import os
import streamlit as st
from pymongo import MongoClient
from pymongo.errors import PyMongoError
import vertexai
from vertexai.language_models import TextEmbeddingModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_google_vertexai import ChatVertexAI

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "sunny-jetty-440519-r1-34e60f63fa6e.json"

# Streamlit page setup
st.set_page_config(page_title="SmartStudy Tutor", page_icon="😎")
st.title("SmartStudy - Your IA Tutor")

# Env vars
PROJECT_ID = os.environ.get("PROJECT_ID")       # Required, no default
REGION = os.environ.get("REGION","europe-west1")
ATLAS_URI = os.environ.get("ATLAS_URI")         # Required, no default
MONGODB_DB = os.environ.get("MONGODB_DB", "chat-rag")
MONGODB_COLLECTION = os.environ.get("MONGODB_COLLECTION", "context")
VECTOR_INDEX = os.environ.get("VECTOR_INDEX", "autoembed_index")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-005")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

SYSTEM_INSTRUCTION = """You are SmartStudy, a Formal Academic Tutor. Your role is to guide students through course material with clarity, rigor, and pedagogical intent.

## YOUR IDENTITY
- You are a knowledgeable, patient, and encouraging academic tutor.
- You hold yourself to the highest standards of academic integrity.
- You never speculate or fabricate information.

## CORE RULES (non-negotiable)
1. **Grounded answers only**: You MUST answer exclusively from the provided context passages. If the context does not contain sufficient information, clearly state: "The course material provided does not contain enough information to answer this question confidently."
2. **Cite every claim**: After each substantive point, cite its source in the format → `[source: gs://bucket/filename, chunk #N]`
3. **No hallucination**: Never invent facts, definitions, or examples that are not present in the context.
4. **Honest uncertainty**: If you are unsure or the context is ambiguous, say so explicitly.

## RESPONSE STRUCTURE
Structure every response as follows:

### Answer
Provide a clear, well-organized explanation based strictly on the retrieved context. Use plain language suitable for a student encountering this material. Break complex ideas into steps or bullet points when helpful.

### Sources Used
List every source passage you drew from:
- `[source, chunk #N]` — brief description of what this passage contributed.

### Comprehension Check
End with exactly ONE pedagogical follow-up question that:
- Tests whether the student understood the key concept you just explained.
- Cannot be answered with a simple "yes" or "no".
- Is directly grounded in the content you cited.

## SPECIAL COMMANDS
- If the student types `/quiz`, generate a quiz (handled separately).
- If the student types `/summary`, produce a structured summary of all indexed content.
- If the student types `/explain <concept>`, focus your entire response on explaining that concept from the documents.

## TONE
- Formal but approachable. Think: a brilliant professor who genuinely wants you to succeed.
- Encouraging when a student shows understanding.
- Corrective but kind when a student misunderstands.
- Never condescending, never dismissive.
"""


# AI helpers
@st.cache_resource
def init_vertexai():
    try:
        vertexai.init(project=PROJECT_ID, location=REGION)
    except Exception as e:
        st.error(f"Vertex AI init failed: {e}")


def embed_query(question: str):
    try:
        model = TextEmbeddingModel.from_pretrained(EMBEDDING_MODEL)
        embedding = model.get_embeddings([question])[0]
        return embedding.values
    except Exception as e:
        st.error(f"Google API issue: Impossible to generate the embedding : {e}")
        return None


def retrieve_context(question: str, k: int = 4):
    query_embedding = embed_query(question)
    # if embedding fails
    if query_embedding is None:
        return []  

    client = None
    try:
        # 5s DB timeout so the app won't hang
        client = MongoClient(ATLAS_URI, serverSelectionTimeoutMS=5000)
        collection = client[MONGODB_DB][MONGODB_COLLECTION]

        pipeline = [
            {"$vectorSearch": {"index": VECTOR_INDEX, "path": "embedding", "queryVector": query_embedding,
                               "numCandidates": 100, "limit": k}},
            {"$project": {"_id": 0, "text": 1, "source": 1, "chunk_index": 1, "score": {"$meta": "vectorSearchScore"}}}
        ]
        docs = list(collection.aggregate(pipeline))
        return docs
    except PyMongoError as e:
        st.error(f"MongoDB Atlas connection failed: {e}")
        return []
    finally:
        if client:
            client.close()


def build_context(docs):
    if not docs:
        return "No relevant context found due to a system error or empty database."
    parts = []
    for i, doc in enumerate(docs, start=1):
        parts.append(f"Source {i} ({doc.get('source')}): {doc.get('text')}")
    return "\n\n---\n\n".join(parts)


# Chat UI
init_vertexai()

if "messages" not in st.session_state:
    st.session_state.messages = []

# Show chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# When the user sends a message
if prompt := st.chat_input("Ask me anything about your course material..."):
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.spinner("Thinking..."):
        # 1) Fetch context
        docs = retrieve_context(prompt)
        context = build_context(docs)

        # 2) Build prompt template
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_INSTRUCTION),
            ("user", "Document context:\n{context}\n\nStudent question:\n{question}")
        ])

        try:
            # 3) Init Gemini via LangChain
            # Add a request timeout
            llm = ChatVertexAI(
                model_name=GEMINI_MODEL,
                project=PROJECT_ID,
                location=REGION,
                request_timeout=10.0  # Max 10s
            )

            # 4) LCEL chain
            rag_chain = prompt_template | llm | StrOutputParser()

            # 5) Run the chain
            response_text = rag_chain.invoke({"context": context, "question": prompt})

            # Show the answer
            with st.chat_message("assistant"):
                st.markdown(response_text)
            st.session_state.messages.append({"role": "assistant", "content": response_text})

        except Exception as e:
            # If Gemini/LangChain dies (timeout, ...), don't crash the ui
            error_msg = f"Sorry, I'm having technical issues right now (timeout/API). Try again. Details: {e}"
            with st.chat_message("assistant"):
                st.error(error_msg)
            st.session_state.messages.append({"role": "assistant", "content": error_msg})