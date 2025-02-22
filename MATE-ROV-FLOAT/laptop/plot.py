import json
import matplotlib.pyplot as plt

def main():
    # 1) Read the JSON file
    #    Replace 'data.json' with the actual filename if different
    with open('coordinates.json', 'r') as f:
        data = json.load(f)

    # 2) Sort by the "time" key
    data_sorted = sorted(data, key=lambda x: x["time"])

    # 3) Extract time, depth, and pressure lists
    times = [item["time"] for item in data_sorted]
    depths = [item["depth"] for item in data_sorted]
    pressures = [item["pressure"] for item in data_sorted]

    # 4) Plot two subplots
    plt.figure(figsize=(10, 6))

    # Subplot 1: Time vs. Depth
    plt.subplot(2, 1, 1)
    plt.plot(times, depths, marker='o', linestyle='-')
    plt.xlabel("Time (s)")
    plt.ylabel("Depth (m)")
    plt.title("Time vs Depth")

    # Subplot 2: Time vs. Pressure
    plt.subplot(2, 1, 2)
    plt.plot(times, pressures, marker='o', linestyle='-')
    plt.xlabel("Time (s)")
    plt.ylabel("Pressure (units)")
    plt.title("Time vs Pressure")

    # 5) Main title
    plt.suptitle("Company Number: 6969", fontsize=14)

    plt.tight_layout()
    plt.show()

if __name__ == '__main__':
    main()
