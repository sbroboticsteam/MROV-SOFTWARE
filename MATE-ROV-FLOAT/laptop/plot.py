# filepath: /c:/Users/ruthv/OneDrive/Desktop/Robotics/MROV-SOFTWARE/MATE-ROV-FLOAT/laptop/plot.py
import json
import matplotlib.pyplot as plt

def main():
    # 1) Read the JSON file
    with open('coordinates.json', 'r') as f:
        data = json.load(f)

    # 2) Sort by the "time" key
    data_sorted = sorted(data, key=lambda x: x["time"])

    # 3) Extract time, depth, and pressure lists
    times = [item["time"] for item in data_sorted]
    depths = [item["depth"] for item in data_sorted]
    pressures = [item["pressure"] for item in data_sorted]

    # --- Compute velocity (m/s) from depth and time arrays ---
    # Velocity[i] = (depths[i+1] - depths[i]) / (times[i+1] - times[i])
    velocity = []
    for i in range(len(depths) - 1):
        dt = times[i+1] - times[i]
        dd = depths[i+1] - depths[i]
        if dt != 0:
            velocity.append(dd / dt)
        else:
            velocity.append(0.0)
    velocity_times = times[1:]  # Align velocity array with time

    # 4) Plot three subplots: depth, pressure, and velocity
    plt.figure(figsize=(10, 8))

    # Subplot 1: Time vs. Depth
    plt.subplot(3, 1, 1)
    plt.plot(times, depths, marker='o', linestyle='-')
    plt.xlabel("Time (s)")
    plt.ylabel("Depth (m)")
    plt.title("Time vs Depth")

    # Subplot 2: Time vs. Pressure
    plt.subplot(3, 1, 2)
    plt.plot(times, pressures, marker='o', linestyle='-')
    plt.xlabel("Time (s)")
    plt.ylabel("Pressure (units)")
    plt.title("Time vs Pressure")

    # Subplot 3: Time vs. Velocity
    plt.subplot(3, 1, 3)
    plt.plot(velocity_times, velocity, marker='o', linestyle='-')
    plt.xlabel("Time (s)")
    plt.ylabel("Velocity (m/s)")
    plt.title("Time vs Velocity")

    # 5) Main title
    plt.suptitle("Company Number: 6969", fontsize=14)

    plt.tight_layout()
    plt.show()

if __name__ == '__main__':
    main()
