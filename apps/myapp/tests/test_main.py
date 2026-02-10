from myapp import main


def test_main(capsys: object) -> None:
    main()
    # If we get here without error, the import chain works
