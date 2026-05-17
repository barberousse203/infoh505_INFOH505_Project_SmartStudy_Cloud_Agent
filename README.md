# SmartStudy Tutor - README

## Prerequisites

Before launching the application, you must configure the following environment variables:

### 1. **Google Cloud Project ID**
```bash
PROJECT_ID = os.environ.get("PROJECT_ID","Your_project_ID")         # Required, no default
```

### 2. **MongoDB Atlas URI**
```bash
ATLAS_URI = os.environ.get("ATLAS_URI","mongodb+srv://...")         # Required, no default                
```

### 3. **Google Cloud Credentials File**
Ensure the file `.json` (your Google Cloud credentials) is located in the project root directory.


---

## Launching the Application

Once environment variables are configured, start Streamlit with:

```bash
streamlit run app.py
```

The application will automatically open in your browser at `http://localhost:8501`.

---

## Features

- Interactive chat with an academic AI tutor
- Vector search in MongoDB Atlas
- Course source citations
- Comprehension check after each response
