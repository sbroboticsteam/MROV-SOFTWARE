
# MROV-SOFTWARE

Welcome to the **MROV-SOFTWARE** repository, the home for the software team of MROV. This document will guide you through setting up the repository on your local machine, the development workflow, and contribution guidelines.

---

## **Table of Contents**
1. [Prerequisites](#prerequisites)
2. [Repository Setup](#repository-setup)
3. [Development Workflow](#development-workflow)
4. [Contribution Guidelines](#contribution-guidelines)
5. [Example Commands](#example-commands)

---

## **Prerequisites**
Before getting started, make sure you have the following tools installed:
- [Git](https://git-scm.com/downloads): Version control tool
- A code editor or IDE (e.g., [VS Code](https://code.visualstudio.com/))

### **Installing Git**
1. Download Git from the [official website](https://git-scm.com/downloads).
2. Follow the installation instructions for your operating system.
3. Verify the installation by running the following command in a terminal:
   ```bash
   git --version
   ```
   You should see the installed Git version.

---

## **Repository Setup**
1. Open your terminal.
2. Clone this repository using the following command:
   ```bash
   git clone https://github.com/sbroboticsteam/MROV-SOFTWARE.git
   ```
3. Navigate to the repository folder:
   ```bash
   cd MROV-SOFTWARE
   ```

---

## **Development Workflow**
### **1. Create Your Own Branch**
Changes to the `main` branch are not allowed directly. Each contributor must create their own branch and work on it. The branch name should include your name for easy identification.

**To create a new branch:**
```bash
git checkout -b <your-name/feature-description>
```

For example:
```bash
git checkout -b ruthvick/motor-control-update
```

### **2. Make Changes**
- Edit the code as needed in your branch.
- Test your changes locally.

### **3. Stage and Commit Changes**
After making your changes, stage and commit them:
```bash
git add .
git commit -m "Your descriptive commit message"
```

### **4. Push Changes to Remote**
Push your branch to the remote repository:
```bash
git push origin <your-branch-name>
```

Example:
```bash
git push origin ruthvick/motor-control-update
```

### **5. Create a Pull Request**
1. Go to the [MROV-SOFTWARE GitHub repository](https://github.com/sbroboticsteam/MROV-SOFTWARE).
2. Navigate to the **Pull Requests** tab.
3. Click **New Pull Request**.
4. Select your branch as the source and `main` as the target.
5. Add a meaningful title and description, then click **Create Pull Request**.

---

## **Contribution Guidelines**
1. **No Direct Changes to `main`:** All changes must be made in individual branches.
2. **Pull Requests:** Ensure your code is functional and thoroughly tested before creating a pull request.
3. **Code Reviews:** Your pull request will be reviewed by a team member before being merged into `main`.
4. **Branch Naming Convention:** Use a descriptive branch name, such as `<your-name/feature-description>`.

---

## **Example Commands**
### **Cloning the Repository**
```bash
git clone https://github.com/sbroboticsteam/MROV-SOFTWARE.git
cd MROV-SOFTWARE
```

### **Creating a New Branch**
```bash
git checkout -b ruthvick/motor-control-update
```

### **Staging and Committing Changes**
```bash
git add .
git commit -m "Added motor control logic for 8 motors"
```

### **Pushing the Branch**
```bash
git push origin ruthvick/motor-control-update
```

### **Creating a Pull Request**
1. Go to [Pull Requests](https://github.com/sbroboticsteam/MROV-SOFTWARE/pulls).
2. Select your branch and create the pull request.

---

## **Notes**
- Always sync your local repository with the remote `main` branch before creating a new branch:
  ```bash
  git fetch origin
  git checkout main
  git pull origin main
  ```

Happy coding!
