# SmartStudy Cloud Agent

SmartStudy is a cloud-native academic tutor built for the INFO-H505 Cloud Computing project.  
The application lets users upload lecture PDFs to Google Cloud Storage, automatically indexes their content, and then allows students to ask questions through a Streamlit chat interface.

The system uses a Retrieval-Augmented Generation architecture:

```text
PDF upload to Google Cloud Storage
→ Cloud Function triggered by Eventarc
→ PDF text extraction
→ LangChain chunking
→ Vertex AI embeddings
→ MongoDB Atlas Vector Search
→ Streamlit RAG tutor
→ Gemini 2.5 Flash answer
```

## Repository Structure

```text
infoh505_INFOH505_Project_SmartStudy_Cloud_Agent/
├── cloud_function/
│   ├── main.py
│   └── requirements.txt
│
├── streamlit_app/
│   ├── app.py
│   └── requirements.txt
│
└── README.md
```

## Main Components

### `cloud_function/`

This folder contains the ingestion pipeline.

When a PDF is uploaded to the Google Cloud Storage bucket, the Cloud Function:

1. receives the GCS upload event,
2. checks that the uploaded file is a PDF,
3. downloads the PDF temporarily,
4. extracts text using `pypdf`,
5. splits the text into chunks with LangChain,
6. generates embeddings with Vertex AI,
7. upserts the chunks and vectors into MongoDB Atlas.

### `streamlit_app/`

This folder contains the user interface and RAG logic.

The Streamlit app:

1. receives a student question,
2. embeds the question with Vertex AI,
3. retrieves relevant chunks from MongoDB Atlas Vector Search,
4. builds a grounded prompt with LangChain,
5. sends the prompt to Gemini 2.5 Flash,
6. displays a tutor-style answer with sources.

## Prerequisites

You need:

* a Google Cloud project,
* Google Cloud CLI installed or Cloud Shell,
* a MongoDB Atlas cluster,
* Vertex AI enabled,
* a MongoDB Atlas Vector Search index,
* Python 3.11 or higher.

## MongoDB Atlas Setup

Create a MongoDB Atlas database and collection for the document chunks.

Recommended structure:

```text
Database: chat-rag
Collection: context
Vector field: embedding
Text field: text
Vector index: autoembed_index
Embedding dimensions: 768
```

The vector index must be created in MongoDB Atlas on the `embedding` field.

Example Vector Search index configuration:

```json
{
  "fields": [
    {
      "type": "vector",
      "path": "embedding",
      "numDimensions": 768,
      "similarity": "euclidean"
    }
  ]
}
```

The exact database name, collection name, and index name are configurable through environment variables.

## Google Cloud Setup

Set your main variables:

```bash
export PROJECT_ID="your-project-id"
export REGION="us-central1"
export BUCKET_NAME="your-gcs-bucket-name"
export FUNCTION_NAME="smartstudy-ingest-pdf"

export MONGODB_DB="chat-rag"
export MONGODB_COLLECTION="context"
export VECTOR_INDEX="autoembed_index"
export EMBEDDING_MODEL="text-embedding-005"
export GEMINI_MODEL="gemini-2.5-flash"
```

Set the active project:

```bash
gcloud config set project $PROJECT_ID
```

Enable the required Google Cloud APIs:

```bash
gcloud services enable \
  storage.googleapis.com \
  cloudfunctions.googleapis.com \
  cloudbuild.googleapis.com \
  eventarc.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  pubsub.googleapis.com \
  aiplatform.googleapis.com \
  logging.googleapis.com \
  secretmanager.googleapis.com
```

Create the GCS bucket:

```bash
gcloud storage buckets create gs://$BUCKET_NAME \
  --location=$REGION \
  --uniform-bucket-level-access
```

## Secret Manager Setup

Do not hardcode the MongoDB Atlas URI in the code.

Create a secret for the MongoDB connection string:

```bash
echo -n "mongodb+srv://USER:PASSWORD@CLUSTER.mongodb.net/?retryWrites=true&w=majority" | \
gcloud secrets create ATLAS_URI --data-file=-
```

Give the Cloud Function service account access to the secret:

```bash
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")

gcloud secrets add-iam-policy-binding ATLAS_URI \
  --member="serviceAccount:$PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

## Deploy the Cloud Function

Go to the Cloud Function folder:

```bash
cd cloud_function
```

Deploy the ingestion function:

```bash
gcloud functions deploy "$FUNCTION_NAME" \
  --gen2 \
  --runtime=python311 \
  --region="$REGION" \
  --source=. \
  --entry-point=ingest_pdf \
  --trigger-bucket="$BUCKET_NAME" \
  --trigger-location="$REGION" \
  --memory=1Gi \
  --timeout=540s \
  --max-instances=1 \
  --set-env-vars="PROJECT_ID=$PROJECT_ID,REGION=$REGION,MONGODB_DB=$MONGODB_DB,MONGODB_COLLECTION=$MONGODB_COLLECTION,EMBEDDING_MODEL=$EMBEDDING_MODEL" \
  --set-secrets="ATLAS_URI=ATLAS_URI:latest"
```

Check the function:

```bash
gcloud functions describe "$FUNCTION_NAME" \
  --gen2 \
  --region="$REGION"
```

## Upload a PDF

Upload a PDF into the bucket:

```bash
gcloud storage cp my-course.pdf gs://$BUCKET_NAME/pdfs/my-course.pdf
```

Read the Cloud Function logs:

```bash
gcloud functions logs read "$FUNCTION_NAME" \
  --region="$REGION" \
  --gen2 \
  --limit=100
```

Expected behavior:

```text
SmartStudy ingestion triggered
Downloaded PDF
Extracted text
Created chunks
Embedded chunks
MongoDB upsert complete
SmartStudy PDF ingestion finished successfully
```

## Run the Streamlit App

Go to the Streamlit folder:

```bash
cd streamlit_app
```

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Set the required environment variables:

```bash
export PROJECT_ID="your-project-id"
export REGION="us-central1"

export ATLAS_URI="mongodb+srv://USER:PASSWORD@CLUSTER.mongodb.net/?retryWrites=true&w=majority"

export MONGODB_DB="chat-rag"
export MONGODB_COLLECTION="context"
export VECTOR_INDEX="autoembed_index"
export EMBEDDING_MODEL="text-embedding-005"
export GEMINI_MODEL="gemini-2.5-flash"
```

Run the app:

```bash
streamlit run app.py
```

Then open the local Streamlit URL in your browser and ask questions about the uploaded PDFs.

## Tutor Behavior

SmartStudy is instructed to behave as a formal academic tutor.
It must:

* answer only from the retrieved document context,
* cite the source chunks,
* avoid hallucinations,
* say when the documents do not contain enough information,
* end with a short comprehension question.

This makes the application useful for studying lecture material rather than acting as a generic chatbot.

## Notes and Limitations

The current implementation extracts text from PDFs using `pypdf`. Scanned PDFs or image-heavy documents may not be parsed correctly unless OCR or multimodal processing is added.

If several PDFs are stored in the same MongoDB collection, retrieval may mix chunks from different documents. A recommended improvement is to let the user select a document in the Streamlit interface and apply a MongoDB filter on `object_name`.
