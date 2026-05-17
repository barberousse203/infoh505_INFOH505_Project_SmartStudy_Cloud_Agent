
import os

import hashlib

from pathlib import Path



import functions_framework

from google.cloud import storage

import vertexai

from vertexai.language_models import TextEmbeddingModel

from pymongo import MongoClient, UpdateOne

from pypdf import PdfReader

from langchain_text_splitters import RecursiveCharacterTextSplitter





PROJECT_ID = os.environ.get("PROJECT_ID")

REGION = os.environ.get("REGION", "us-central1")



ATLAS_URI = os.environ.get("ATLAS_URI")

MONGODB_DB = os.environ.get("MONGODB_DB", "chat-rag")

MONGODB_COLLECTION = os.environ.get("MONGODB_COLLECTION", "context")



EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-005")





def download_pdf(bucket_name: str, object_name: str) -> str:

    storage_client = storage.Client()

    bucket = storage_client.bucket(bucket_name)

    blob = bucket.blob(object_name)



    local_path = f"/tmp/{Path(object_name).name}"

    blob.download_to_filename(local_path)



    print(f"Downloaded PDF to {local_path}")

    return local_path





def extract_text_from_pdf(local_path: str) -> str:

    reader = PdfReader(local_path)

    pages_text = []



    for page_number, page in enumerate(reader.pages, start=1):

        text = page.extract_text() or ""

        if text.strip():

            pages_text.append(f"\n\n--- Page {page_number} ---\n{text}")



    full_text = "\n".join(pages_text).strip()

    print(f"Extracted {len(full_text)} characters from PDF")

    return full_text





def chunk_text(text: str):

    splitter = RecursiveCharacterTextSplitter(

        chunk_size=1000,

        chunk_overlap=200,

    )



    chunks = splitter.split_text(text)

    print(f"Created {len(chunks)} chunks")

    return chunks





def embed_chunks(chunks):

    vertexai.init(project=PROJECT_ID, location=REGION)

    model = TextEmbeddingModel.from_pretrained(EMBEDDING_MODEL)



    all_embeddings = []

    batch_size = 5



    for i in range(0, len(chunks), batch_size):

        batch = chunks[i:i + batch_size]

        embeddings = model.get_embeddings(batch)

        all_embeddings.extend([embedding.values for embedding in embeddings])

        print(f"Embedded chunks {i + 1} to {i + len(batch)}")



    return all_embeddings





def upsert_chunks_to_mongodb(bucket_name, object_name, chunks, embeddings):

    if not ATLAS_URI:

        raise ValueError("ATLAS_URI environment variable is missing")



    client = MongoClient(ATLAS_URI)

    collection = client[MONGODB_DB][MONGODB_COLLECTION]



    source = f"gs://{bucket_name}/{object_name}"

    operations = []



    for index, (chunk, embedding) in enumerate(zip(chunks, embeddings)):

        stable_id = hashlib.sha256(f"{source}#chunk-{index}".encode("utf-8")).hexdigest()



        doc = {

            "_id": stable_id,

            "text": chunk,

            "embedding": embedding,

            "source": source,

            "chunk_index": index,

            "bucket": bucket_name,

            "object_name": object_name,

        }



        operations.append(

            UpdateOne(

                {"_id": stable_id},

                {"$set": doc},

                upsert=True,

            )

        )



    if operations:

        result = collection.bulk_write(operations)

        print(

            f"MongoDB upsert complete: "

            f"matched={result.matched_count}, "

            f"modified={result.modified_count}, "

            f"upserted={len(result.upserted_ids)}"

        )

    else:

        print("No chunks to upsert")



    client.close()





@functions_framework.cloud_event

def ingest_pdf(cloud_event):

    data = cloud_event.data



    bucket_name = data.get("bucket")

    object_name = data.get("name")

    content_type = data.get("contentType")



    print("SmartStudy ingestion triggered")

    print(f"Bucket: {bucket_name}")

    print(f"File name: {object_name}")

    print(f"Content type: {content_type}")



    if not object_name or not object_name.lower().endswith(".pdf"):

        print("Not a PDF file. Skipping.")

        return



    local_pdf = download_pdf(bucket_name, object_name)

    text = extract_text_from_pdf(local_pdf)



    if not text:

        print("No extractable text found in PDF. Skipping.")

        return



    chunks = chunk_text(text)

    embeddings = embed_chunks(chunks)

    upsert_chunks_to_mongodb(bucket_name, object_name, chunks, embeddings)



    print("SmartStudy PDF ingestion finished successfully")

