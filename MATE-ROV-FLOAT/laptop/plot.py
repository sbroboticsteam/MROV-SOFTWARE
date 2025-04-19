import json
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np

def main():
    # 1) Read the JSON file
    with open('coordinates.json', 'r') as f:
        data = json.load(f)

    # 2) Sort by the "time" key
    data_sorted = sorted(data, key=lambda x: x["time"])

    # 3) Extract time, depth, and pressure lists
    times = [item["time"] for item in data_sorted]
    depths_raw = [item["depth"] for item in data_sorted]
    pressures = [item["pressure"] for item in data_sorted]
    
    # --- Clip depth values to our display range ---
    depths = []
    for d in depths_raw:
        if d < -1:
            depths.append(-1)
        elif d > 4:
            depths.append(4)
        else:
            depths.append(d)

    # --- Compute velocity (m/s) from depth and time arrays ---
    # Velocity[i] = (depths[i+1] - depths[i]) / (times[i+1] - times[i])
    velocity_raw = []
    for i in range(len(depths) - 1):
        dt = times[i+1] - times[i]
        dd = depths[i+1] - depths[i]
        if dt != 0:
            velocity_raw.append(dd / dt)
        else:
            velocity_raw.append(0.0)
    
    # --- Clip velocity values to our display range ---
    velocity = []
    for v in velocity_raw:
        if v < -1:
            velocity.append(-1)
        elif v > 1:
            velocity.append(1)
        else:
            velocity.append(v)
            
    velocity_times = times[:-1]  # Align velocity array with time

    # 4) Create interactive subplot figure with Plotly - only 2 subplots now
    fig = make_subplots(
        rows=2, 
        cols=1,
        subplot_titles=("Time vs Depth", "Time vs Velocity"),
        vertical_spacing=0.2
    )

    # Add traces for each subplot
    # Subplot 1: Time vs. Depth
    fig.add_trace(
        go.Scatter(
            x=times, 
            y=depths, 
            mode='lines+markers',
            name='Depth',
            hovertemplate='Time: %{x:.2f}s<br>Depth: %{y:.3f}m'
        ),
        row=1, col=1
    )
    
    # Add reference lines for target depth range as actual traces (making them interactive)
    fig.add_trace(
        go.Scatter(
            x=[min(times), max(times)],
            y=[2.5, 2.5],
            mode='lines',
            name='Min Target Depth (2.5m)',
            line=dict(color="red", width=2, dash="dash"),
            hoverinfo='name'
        ),
        row=1, col=1
    )
    
    fig.add_trace(
        go.Scatter(
            x=[min(times), max(times)],
            y=[2.75, 2.75],
            mode='lines',
            name='Max Target Depth (2.75m)',
            line=dict(color="red", width=2, dash="dash"),
            hoverinfo='name'
        ),
        row=1, col=1
    )

    # Subplot 2: Time vs. Velocity
    fig.add_trace(
        go.Scatter(
            x=velocity_times, 
            y=velocity, 
            mode='lines+markers',
            name='Velocity',
            hovertemplate='Time: %{x:.2f}s<br>Velocity: %{y:.3f}m/s'
        ),
        row=2, col=1
    )
    
    # Add reference lines for velocity limits as actual traces (making them interactive)
    fig.add_trace(
        go.Scatter(
            x=[min(times), max(times)],
            y=[0.18, 0.18],
            mode='lines',
            name='Max Descent Velocity (0.18 m/s)',
            line=dict(color="orange", width=2, dash="dash"),
            hoverinfo='name'
        ),
        row=2, col=1
    )
    
    fig.add_trace(
        go.Scatter(
            x=[min(times), max(times)],
            y=[-0.1, -0.1],
            mode='lines',
            name='Max Ascent Velocity (-0.1 m/s)',
            line=dict(color="orange", width=2, dash="dash"),
            hoverinfo='name'
        ),
        row=2, col=1
    )

    # Update layout with improved formatting
    fig.update_layout(
        title_text=f"Company Number: 6969",
        height=700,
        width=1000,
        showlegend=True,  # Now show legend to toggle reference lines
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        hovermode='closest'
    )
    
    # Update axes labels and configure fixed dtick (step size) of 0.5
    fig.update_xaxes(title_text="Time (s)", row=1, col=1)
    fig.update_yaxes(
        title_text="Depth (m)", 
        row=1, col=1,
        # Invert y-axis for depth (positive values below zero)
        autorange="reversed",
        # Set fixed y-axis range (-1 to 4)
        range=[-1, 4],
        # Set y-axis tick interval to 0.5
        dtick=0.5
    )
    
    fig.update_xaxes(title_text="Time (s)", row=2, col=1)
    fig.update_yaxes(
        title_text="Velocity (m/s)", 
        row=2, col=1,
        # Set fixed y-axis range
        range=[-1, 1],
        # Set y-axis tick interval to 0.5
        dtick=0.5
    )

    # Show the interactive figure
    fig.show()

if __name__ == '__main__':
    main()