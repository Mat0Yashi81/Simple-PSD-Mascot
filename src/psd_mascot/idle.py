"""Timed idle actions; all deadlines are transient and never stored in presets."""
import math
import random
import time
from uuid import uuid4
from PySide6.QtCore import QObject,QEvent,Qt,Signal
from PySide6.QtWidgets import (QCheckBox,QComboBox,QDoubleSpinBox,QFormLayout,
    QHBoxLayout,QLabel,QLineEdit,QListWidget,QListWidgetItem,QPushButton,
    QScrollArea,QVBoxLayout,QWidget)
from .ordering import ReorderButtons


def _seconds(value,default,maximum):
    try:
        number=float(value)
        return round(max(.1,min(maximum,number)),1) if math.isfinite(number) else default
    except (ValueError,TypeError,OverflowError):return default


def sanitize_idle(value):
    value=value if isinstance(value,dict) else {}
    low=_seconds(value.get('min_seconds'),30.,86400.)
    high=_seconds(value.get('max_seconds'),60.,86400.)
    low,high=sorted((low,high))
    actions=[];used=set()
    items=value.get('actions',[])
    for item in items if isinstance(items,list) else []:
        if not isinstance(item,dict):continue
        identifier=str(item.get('id') or uuid4().hex)
        if identifier in used:identifier=uuid4().hex
        used.add(identifier)
        actions.append({'id':identifier,'name':str(item.get('name') or '放置アクション'),
            'enabled':item.get('enabled') if isinstance(item.get('enabled'),bool) else True,
            'expression':str(item.get('expression') or ''),'voice':str(item.get('voice') or ''),
            'duration':_seconds(item.get('duration'),2.,600.)})
    return {'enabled':value.get('enabled') if isinstance(value.get('enabled'),bool) else True,
            'min_seconds':low,'max_seconds':high,'actions':actions}


class IdleScheduler:
    def __init__(self,clock=None,rng=None):
        self.clock=clock or time.monotonic
        self.rng=rng or random.Random()
        self.deadline=None
    def reset(self):self.deadline=None
    def arm(self,low,high):self.deadline=self.clock()+self.rng.uniform(low,high)
    def poll(self,low,high,*,paused=False,ready=True):
        if paused:self.reset();return False
        if self.deadline is None:self.arm(low,high);return False
        if ready and self.clock()>=self.deadline:self.reset();return True
        return False
    def choose(self,actions):return self.rng.choice(actions)


class IdleActivityFilter(QObject):
    activity=Signal()
    INPUT_EVENTS={QEvent.Type.MouseButtonPress,QEvent.Type.MouseButtonRelease,
        QEvent.Type.MouseButtonDblClick,QEvent.Type.MouseMove,QEvent.Type.Wheel,
        QEvent.Type.KeyPress,QEvent.Type.TouchBegin,QEvent.Type.TouchUpdate,
        QEvent.Type.TabletPress,QEvent.Type.TabletMove,QEvent.Type.ContextMenu}
    def __init__(self,main,mascot):
        super().__init__(main);self.roots=(main,mascot)
    def eventFilter(self,watched,event):
        if event.type() in self.INPUT_EVENTS and isinstance(watched,QWidget):
            if any(watched is root or root.isAncestorOf(watched) for root in self.roots):
                self.activity.emit()
        return False


class IdlePanel(QScrollArea):
    add_requested=Signal()
    delete_requested=Signal(str)
    edited=Signal(str,object)
    options_changed=Signal(object)
    test_requested=Signal(str)
    move_requested=Signal(str,int)
    def __init__(self):
        super().__init__();self.setWidgetResizable(True)
        self._updating=False;self._actions=[];self._expressions=[];self._voices=[]
        body=QWidget();self.setWidget(body);layout=QVBoxLayout(body)
        hint=QLabel('マスコット・このアプリを操作しない時間が続くと、設定範囲からランダムに待ち時間を選び、有効なアクションを1つ実行します。')
        hint.setWordWrap(True);layout.addWidget(hint)
        self.enabled_check=QCheckBox('放置アクションを有効にする');self.enabled_check.setChecked(True)
        layout.addWidget(self.enabled_check)
        timing=QFormLayout();timing.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.min_seconds=self._spin(86400,30);self.max_seconds=self._spin(86400,60)
        timing.addRow('放置時間の下限',self.min_seconds);timing.addRow('放置時間の上限',self.max_seconds)
        layout.addLayout(timing)
        self.status_label=QLabel('アクションを追加してください');self.status_label.setWordWrap(True);layout.addWidget(self.status_label)
        self.action_list=QListWidget();self.action_list.setMinimumHeight(100)
        self.action_list.currentItemChanged.connect(lambda *_:self._show_action());layout.addWidget(self.action_list,1)
        self.reorder_buttons=ReorderButtons(self.action_list)
        self.reorder_buttons.move_requested.connect(lambda step:self.move_requested.emit(self.selected_id(),step));layout.addWidget(self.reorder_buttons)
        row=QHBoxLayout();self.add_button=QPushButton('放置アクションを追加');self.delete_button=QPushButton('削除')
        self.add_button.clicked.connect(lambda:self.add_requested.emit())
        self.delete_button.clicked.connect(lambda:self.delete_requested.emit(self.selected_id()))
        row.addWidget(self.add_button);row.addWidget(self.delete_button);layout.addLayout(row)
        form=QFormLayout();form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.name_edit=QLineEdit();self.name_edit.setPlaceholderText('例：待機中のひとこと')
        self.action_enabled_check=QCheckBox('このアクションを有効にする')
        self.expression_combo=QComboBox();self.voice_combo=QComboBox();self.duration=self._spin(600,2)
        form.addRow('アクション名',self.name_edit);form.addRow(self.action_enabled_check)
        form.addRow('呼び出す表情',self.expression_combo);form.addRow('呼び出すセリフ',self.voice_combo);form.addRow('持続時間',self.duration)
        layout.addLayout(form)
        self.test_button=QPushButton('選択した放置アクションを試す')
        self.test_button.clicked.connect(lambda:self.test_requested.emit(self.selected_id()));layout.addWidget(self.test_button)
        note=QLabel('待ち時間は全アクション共通です。自動実行は立ち絵のデスクトップ表示中に行い、操作すると待ち時間を取り直します。表情は持続時間後に元へ戻り、セリフは最後まで再生します。')
        note.setWordWrap(True);layout.addWidget(note)
        self.enabled_check.toggled.connect(lambda _:self._options())
        self.min_seconds.valueChanged.connect(lambda _:self._options('min'))
        self.max_seconds.valueChanged.connect(lambda _:self._options('max'))
        self.name_edit.editingFinished.connect(self._commit)
        self.action_enabled_check.toggled.connect(lambda _:self._commit())
        self.expression_combo.currentIndexChanged.connect(lambda _:self._commit())
        self.voice_combo.currentIndexChanged.connect(lambda _:self._commit())
        self.duration.valueChanged.connect(lambda _:self._commit());self._show_action()
    @staticmethod
    def _spin(maximum,default):
        field=QDoubleSpinBox();field.setDecimals(1);field.setRange(.1,maximum);field.setSingleStep(.1)
        field.setSuffix(' 秒');field.setValue(default);field.setKeyboardTracking(False);return field
    def selected_id(self):
        item=self.action_list.currentItem();return item.data(Qt.ItemDataRole.UserRole) if item else ''
    def set_state(self,state,selected=None):
        selected=self.selected_id() if selected is None else selected
        self._updating=True
        self.enabled_check.setChecked(state['enabled']);self.min_seconds.setValue(state['min_seconds']);self.max_seconds.setValue(state['max_seconds'])
        self._actions=state['actions'];self.action_list.clear()
        for action in self._actions:
            item=QListWidgetItem(action['name']+('（無効）' if not action['enabled'] else ''))
            item.setData(Qt.ItemDataRole.UserRole,action['id']);self.action_list.addItem(item)
            if action['id']==selected:self.action_list.setCurrentItem(item)
        self._updating=False;self._show_action()
    def set_expressions(self,names):self._expressions=list(names);self._show_action()
    def set_voices(self,presets):self._voices=list(presets);self._show_action()
    def _show_action(self):
        if self._updating:return
        action=next((a for a in self._actions if a['id']==self.selected_id()),None)
        self._updating=True
        for control in (self.name_edit,self.action_enabled_check,self.expression_combo,self.voice_combo,self.duration,self.test_button):control.setEnabled(action is not None)
        self.expression_combo.clear();self.expression_combo.addItem('(未設定)','')
        for name in self._expressions:self.expression_combo.addItem(name,name)
        self.voice_combo.clear();self.voice_combo.addItem('(未設定)','')
        for preset in self._voices:self.voice_combo.addItem(preset['name'],preset['id'])
        if action:
            if action['expression'] and self.expression_combo.findData(action['expression'])<0:self.expression_combo.addItem('(見つからない表情: '+action['expression']+')',action['expression'])
            if action['voice'] and self.voice_combo.findData(action['voice'])<0:self.voice_combo.addItem('(見つからないセリフ)',action['voice'])
            self.name_edit.setText(action['name']);self.action_enabled_check.setChecked(action['enabled']);self.duration.setValue(action['duration'])
            self.expression_combo.setCurrentIndex(max(0,self.expression_combo.findData(action['expression'])))
            self.voice_combo.setCurrentIndex(max(0,self.voice_combo.findData(action['voice'])))
        else:self.name_edit.clear();self.action_enabled_check.setChecked(False)
        self._updating=False
    def _options(self,source=''):
        if self._updating:return
        self._updating=True
        if self.min_seconds.value()>self.max_seconds.value():
            if source=='min':self.max_seconds.setValue(self.min_seconds.value())
            else:self.min_seconds.setValue(self.max_seconds.value())
        self._updating=False
        self.options_changed.emit({'enabled':self.enabled_check.isChecked(),'min_seconds':self.min_seconds.value(),'max_seconds':self.max_seconds.value()})
    def _commit(self):
        if not self._updating and self.selected_id():
            self.edited.emit(self.selected_id(),{'name':self.name_edit.text().strip() or '放置アクション',
                'enabled':self.action_enabled_check.isChecked(),'expression':self.expression_combo.currentData() or '',
                'voice':self.voice_combo.currentData() or '','duration':self.duration.value()})
