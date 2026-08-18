# Install and run HEVA

HEVA runs locally on Windows, macOS, and Linux. The recommended installation uses Conda so
Python and the extraction libraries are installed together.

## 1. Install Conda

Install [Miniforge](https://github.com/conda-forge/miniforge). On Windows, use the Miniforge
Prompt for the following commands. On macOS or Linux, use a terminal.

## 2. Create the environment

Open this repository folder and run:

```bash
conda env create -f environment.yml
conda activate heva-toolkit
```

If the environment already exists, update it instead:

```bash
conda env update -f environment.yml --prune
conda activate heva-toolkit
```

## 3. Check the installation

```bash
python -m heva.doctor --require app --require extraction
```

The check should finish without missing-component errors.

## 4. Run the app

```bash
python -m heva.app
```

Open <http://127.0.0.1:8000>. Stop HEVA with **Stop HEVA** in the project header or press
**Ctrl+C** in the terminal.

Next: [understand HEVA and validation](HEVA_AND_VALIDATION.md).
