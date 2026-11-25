from scripts.f29 import results_md


def main() -> None:
    results_md.write()
    print(f"Đã ghi {results_md.OUT}")


if __name__ == "__main__":
    main()
