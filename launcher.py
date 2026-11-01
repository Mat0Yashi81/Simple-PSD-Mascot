import sys

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == '--distribution-check':
        from psd_mascot.distribution_check import main
        raise SystemExit(main(sys.argv[2:]))
    from psd_mascot.app import main
    main()
