# Running the app

The app is in the `FINAL_PROJECT_1` directory. Use Python 3.11 or newer.

From the repository root, install the dependencies:

```bash
cd FINAL_PROJECT_1
python -m pip install -r requirements.txt
```

Set up the local database, then launch the Streamlit app:

```bash
python setup_db.py
streamlit run main.py
```

Streamlit will print a local URL (usually `http://localhost:8501`) to open in your browser. Stop the app with **Ctrl+C** in the terminal.
