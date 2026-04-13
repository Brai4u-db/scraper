import csv
import sys


def open_csv(file_path: str, limit: int = 10):
    try:
        with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            rows = list(reader)

        if not rows:
            print("Plik CSV jest pusty.")
            return

        headers = rows[0]
        data = rows[1:]

        print("Nagłówki:")
        print(headers)
        print("\nPierwsze wiersze:\n")

        for i, row in enumerate(data[:limit], start=1):
            print(f"{i}: {row}")

        print(f"\nŁącznie wierszy danych: {len(data)}")

    except FileNotFoundError:
        print("Nie znaleziono pliku.")
    except Exception as e:
        print(f"Błąd: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Użycie:")
        print("python open_csv.py nazwa_pliku.csv [liczba_wierszy]")
        sys.exit(1)

    file_path = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) >= 3 else 10

    open_csv(file_path, limit)