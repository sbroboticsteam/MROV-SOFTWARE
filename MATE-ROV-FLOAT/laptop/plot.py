import json
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
import plotly.io as pio
# Set the renderer to use local resources
pio.renderers.default = "browser"


def main():
    # 1) Read the JSON file
    with open('coordinates.json', 'r') as f:
        data = json.load(f)

    # 2) Sort by the "time" key
    data_sorted = sorted(data, key=lambda x: x["time"])

    # 3) Extract data lists
    times = [item["time"] for item in data_sorted]
    depths_raw = [item["depth"] for item in data_sorted]
    pressures = [item["pressure"] for item in data_sorted]
    
    # Extract debugging info if available
    velocities = []
    pid_outputs = []
    pid_errors = []
    pump_statuses = []
    
    for item in data_sorted:
        # Velocity data - default to calculated value if not directly available
        if "velocity" in item:
            velocities.append(item["velocity"])
        else:
            velocities.append(0.0)  # Will be filled in later
            
        # PID data
        if "pid_output" in item:
            pid_outputs.append(item["pid_output"])
        else:
            pid_outputs.append(0)
            
        if "pid_error" in item:
            pid_errors.append(item["pid_error"])
        else:
            pid_errors.append(0)
            
        if "pump_status" in item:
            pump_statuses.append(item["pump_status"])
        else:
            pump_statuses.append("Unknown")
    
    # Calculate velocity if not provided directly
    if len(velocities) == len(times) and all(v == 0.0 for v in velocities):
        for i in range(len(depths_raw) - 1):
            dt = times[i+1] - times[i]
            dd = depths_raw[i+1] - depths_raw[i]
            if dt != 0:
                velocities[i] = dd / dt
            else:
                velocities[i] = 0.0
        # Last point uses previous velocity
        if len(velocities) > 0:
            velocities[-1] = velocities[-2] if len(velocities) > 1 else 0.0
    
    # Clip depth values to our display range
    depths = []
    for d in depths_raw:
        if d < -1:
            depths.append(-1)
        elif d > 4:
            depths.append(4)
        else:
            depths.append(d)

    # 4) Create interactive subplot figure with 4 subplots now
    fig = make_subplots(
        rows=4, 
        cols=1,
        subplot_titles=("Time vs Depth", "Time vs Velocity", "Time vs PID Output", "Time vs PID Error"),
        vertical_spacing=0.1,
        row_heights=[0.35, 0.25, 0.2, 0.2]
    )

    # Add traces for each subplot
    # Subplot 1: Time vs. Depth
    fig.add_trace(
        go.Scatter(
            x=times, 
            y=depths, 
            mode='lines+markers',
            name='Depth',
            hovertemplate='Time: %{x:.2f}s<br>Depth: %{y:.3f}m<br>Pump: %{text}',
            text=pump_statuses
        ),
        row=1, col=1
    )
    
    # Add reference lines for target depth range
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
            x=times, 
            y=velocities, 
            mode='lines',
            name='Velocity',
            hovertemplate='Time: %{x:.2f}s<br>Velocity: %{y:.3f}m/s'
        ),
        row=2, col=1
    )
    
    # Add reference lines for velocity limits
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
    
    # Subplot 3: Time vs. PID Output
    fig.add_trace(
        go.Scatter(
            x=times, 
            y=pid_outputs, 
            mode='lines',
            name='PID Output',
            hovertemplate='Time: %{x:.2f}s<br>PID Output: %{y}'
        ),
        row=3, col=1
    )
    
    # Add reference lines for PID output deadband
    fig.add_trace(
        go.Scatter(
            x=[min(times), max(times)],
            y=[10, 10],
            mode='lines',
            name='Descend Threshold',
            line=dict(color="blue", width=1, dash="dot"),
            hoverinfo='name'
        ),
        row=3, col=1
    )
    
    fig.add_trace(
        go.Scatter(
            x=[min(times), max(times)],
            y=[-10, -10],
            mode='lines',
            name='Ascend Threshold',
            line=dict(color="blue", width=1, dash="dot"),
            hoverinfo='name'
        ),
        row=3, col=1
    )
    
    # Subplot 4: Time vs. PID Error
    fig.add_trace(
        go.Scatter(
            x=times, 
            y=pid_errors, 
            mode='lines',
            name='PID Error',
            hovertemplate='Time: %{x:.2f}s<br>PID Error: %{y:.3f}m'
        ),
        row=4, col=1
    )
    
    # Add zero reference line for PID error
    fig.add_trace(
        go.Scatter(
            x=[min(times), max(times)],
            y=[0, 0],
            mode='lines',
            name='Zero Error',
            line=dict(color="green", width=1, dash="dot"),
            hoverinfo='name'
        ),
        row=4, col=1
    )

    # Update layout
    fig.update_layout(
        title_text=f"Company Number: 6969 - Float Debugging Information",
        height=1000,  # Increased height for 4 subplots
        width=1000,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        hovermode='closest'
    )
    
    # Update axes labels
    fig.update_xaxes(title_text="Time (s)", row=1, col=1)
    fig.update_yaxes(
        title_text="Depth (m)", 
        row=1, col=1,
        autorange="reversed",
        range=[-1, 4],
        dtick=0.5
    )
    
    fig.update_xaxes(title_text="Time (s)", row=2, col=1)
    fig.update_yaxes(
        title_text="Velocity (m/s)", 
        row=2, col=1,
        range=[-0.5, 0.5],
        dtick=0.1
    )
    
    fig.update_xaxes(title_text="Time (s)", row=3, col=1)
    fig.update_yaxes(
        title_text="PID Output", 
        row=3, col=1,
        range=[-100, 100],
        dtick=20
    )
    
    fig.update_xaxes(title_text="Time (s)", row=4, col=1)
    fig.update_yaxes(
        title_text="PID Error (m)", 
        row=4, col=1,
        range=[-0.5, 0.5],
        dtick=0.1
    )

    # Configure Plotly to include all necessary resources in the HTML
    config = {'include_plotlyjs': True}
    fig.show(config=config)

if __name__ == '__main__':
    main()