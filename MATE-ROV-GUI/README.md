# MATE ROV 2025 Dashboard

## Requirements
- PyQt5
    ```bash
    pip install PyQt5
    ```

## How to contribute

### Working from your local machine
1. Clone this repository to your local machine (ideally in a folder for SBRT): 

    SSH (recommended):
    ```bash
    git clone git@github.com:sbroboticsteam/MATE-ROV-GUI.git 
    ```
    HTTPS:
    ```bash
    git clone https://github.com/sbroboticsteam/MATE-ROV-GUI.git
    ```

2. To start working, navigate to the project directory:
    ```bash
    cd MATE-ROV-GUI
    ```

### Branching Workflow
1. Create a feature branch from `main`:
   ```bash
   git checkout main
   git pull origin main
   git checkout -b component-name
   ```

2. Work on your feature branch and push your changes:
   ```bash
   git add <component-name>
   git commit -m "Your commit message"
   git push origin component-name
   ```

3. Open a pull request to merge your changes into `main`.

### Creating pull request

Once your feature branch is pushed to GitHub, follow these steps to create a pull request:

1. Go to the GitHub page of the repository: MATE ROV GUI.

2. Click on the **Pull requests** tab.

3. Click the **New pull request** button.

4. Select your feature branch (compare branch) and ensure main is selected as the base branch.

5. Provide a clear title for the pull request (e.g., "Add camera display UI").

6. In the description, include details about the changes you made.

7. Submit the pull request by clicking **Create pull request**.