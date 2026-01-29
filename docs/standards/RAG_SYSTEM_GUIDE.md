# RAG SYSTEM GUIDE
## Для Claude Code — LlamaIndex

> **Цель:** Единый стиль разработки RAG систем  
> **Референс:** LlamaIndex официальная документация (docs.llamaindex.ai)  
> **Версия:** LlamaIndex 0.10+, Python 3.11+

---

## 🎯 КЛЮЧЕВЫЕ ПРИНЦИПЫ

```
ВСЕГДА                              НИКОГДА
────────────────────────────────    ────────────────────────────────
✓ IngestionPipeline для загрузки    ✗ Прямая загрузка без pipeline
✓ Chunk size 400-800 для prose      ✗ Огромные chunks (>1500 tokens)
✓ Overlap 10-20% от chunk size      ✗ Нулевой overlap
✓ Metadata extraction               ✗ Chunks без контекста
✓ Hybrid search (vector + BM25)     ✗ Только vector search
✓ Reranking для top-k               ✗ Прямой top-k без rerank
✓ Evaluation (RAGAS)                ✗ RAG без метрик качества
✓ Caching для embeddings            ✗ Повторное вычисление
```

---

## 📁 СТРУКТУРА ПРОЕКТА

```
rag_system/
├── .env                          # API keys
├── .env.example
├── pyproject.toml
├── README.md
│
├── src/
│   ├── __init__.py
│   ├── main.py                   # Entry point
│   │
│   ├── config/                   # Конфигурация
│   │   ├── __init__.py
│   │   └── settings.py           # Pydantic Settings
│   │
│   ├── ingestion/                # Загрузка и обработка
│   │   ├── __init__.py
│   │   ├── loaders.py            # Document loaders
│   │   ├── pipeline.py           # Ingestion pipeline
│   │   └── transformations.py    # Custom transformations
│   │
│   ├── indexing/                 # Индексация
│   │   ├── __init__.py
│   │   ├── vector_store.py       # Vector store setup
│   │   └── index.py              # Index creation
│   │
│   ├── retrieval/                # Поиск
│   │   ├── __init__.py
│   │   ├── retrievers.py         # Retriever configs
│   │   └── rerankers.py          # Reranking
│   │
│   ├── generation/               # Генерация
│   │   ├── __init__.py
│   │   ├── query_engine.py       # Query engines
│   │   └── prompts.py            # Custom prompts
│   │
│   ├── evaluation/               # Оценка качества
│   │   ├── __init__.py
│   │   └── metrics.py            # RAGAS metrics
│   │
│   └── api/                      # API endpoints
│       ├── __init__.py
│       └── routes.py
│
├── data/                         # Исходные документы
│   └── .gitkeep
│
├── storage/                      # Persisted indices
│   └── .gitkeep
│
└── tests/
    ├── __init__.py
    └── test_retrieval.py
```

---

## ⚙️ КОНФИГУРАЦИЯ

### Settings

```python
# src/config/settings.py

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """RAG system configuration."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    
    # LLM
    openai_api_key: SecretStr
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.1
    
    # Embeddings
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    
    # Chunking
    chunk_size: int = 512
    chunk_overlap: int = 50
    
    # Retrieval
    similarity_top_k: int = 10
    rerank_top_n: int = 5
    
    # Vector Store
    vector_store_type: str = "qdrant"  # qdrant, pinecone, chroma
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "documents"
    
    # Paths
    data_dir: str = "./data"
    storage_dir: str = "./storage"


settings = Settings()
```

### LlamaIndex Settings (Global)

```python
# src/config/llm_settings.py

from llama_index.core import Settings as LlamaSettings
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.openai import OpenAIEmbedding

from src.config.settings import settings


def configure_llama_index() -> None:
    """Configure global LlamaIndex settings."""
    
    # LLM
    LlamaSettings.llm = OpenAI(
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        api_key=settings.openai_api_key.get_secret_value(),
    )
    
    # Embeddings
    LlamaSettings.embed_model = OpenAIEmbedding(
        model=settings.embedding_model,
        api_key=settings.openai_api_key.get_secret_value(),
    )
    
    # Chunking defaults
    LlamaSettings.chunk_size = settings.chunk_size
    LlamaSettings.chunk_overlap = settings.chunk_overlap
```

---

## 📥 ЗАГРУЗКА ДОКУМЕНТОВ (INGESTION)

### Document Loaders

```python
# src/ingestion/loaders.py

from pathlib import Path
from typing import List

from llama_index.core import SimpleDirectoryReader, Document
from llama_index.readers.file import PDFReader, DocxReader
from llama_index.readers.web import SimpleWebPageReader


def load_from_directory(
    directory: str | Path,
    recursive: bool = True,
    required_exts: list[str] | None = None,
) -> list[Document]:
    """Load documents from a directory."""
    
    reader = SimpleDirectoryReader(
        input_dir=str(directory),
        recursive=recursive,
        required_exts=required_exts or [".pdf", ".docx", ".txt", ".md"],
        filename_as_id=True,
    )
    
    return reader.load_data(show_progress=True)


def load_from_urls(urls: list[str]) -> list[Document]:
    """Load documents from web URLs."""
    
    reader = SimpleWebPageReader(html_to_text=True)
    return reader.load_data(urls)


def load_pdf(file_path: str | Path) -> list[Document]:
    """Load a single PDF file."""
    
    reader = PDFReader()
    return reader.load_data(file=Path(file_path))


def load_with_metadata(
    directory: str | Path,
    metadata_fn: callable = None,
) -> list[Document]:
    """Load documents with custom metadata extraction."""
    
    def default_metadata_fn(file_path: str) -> dict:
        path = Path(file_path)
        return {
            "file_name": path.name,
            "file_type": path.suffix,
            "directory": str(path.parent),
        }
    
    reader = SimpleDirectoryReader(
        input_dir=str(directory),
        file_metadata=metadata_fn or default_metadata_fn,
    )
    
    return reader.load_data()
```

### Ingestion Pipeline

```python
# src/ingestion/pipeline.py

from llama_index.core import Document
from llama_index.core.ingestion import IngestionPipeline, IngestionCache
from llama_index.core.node_parser import (
    SentenceSplitter,
    SemanticSplitterNodeParser,
    HierarchicalNodeParser,
)
from llama_index.core.extractors import (
    TitleExtractor,
    SummaryExtractor,
    QuestionsAnsweredExtractor,
    KeywordExtractor,
)
from llama_index.embeddings.openai import OpenAIEmbedding

from src.config.settings import settings


# ═══════════════════════════════════════════════════════════════════
# Базовый Pipeline (для начала)
# ═══════════════════════════════════════════════════════════════════

def create_basic_pipeline(
    vector_store=None,
    cache=None,
) -> IngestionPipeline:
    """Create a basic ingestion pipeline."""
    
    return IngestionPipeline(
        transformations=[
            # 1. Chunking
            SentenceSplitter(
                chunk_size=settings.chunk_size,
                chunk_overlap=settings.chunk_overlap,
            ),
            # 2. Embedding
            OpenAIEmbedding(
                model=settings.embedding_model,
                api_key=settings.openai_api_key.get_secret_value(),
            ),
        ],
        vector_store=vector_store,
        cache=cache,
    )


# ═══════════════════════════════════════════════════════════════════
# Advanced Pipeline (с metadata extraction)
# ═══════════════════════════════════════════════════════════════════

def create_advanced_pipeline(
    vector_store=None,
    cache=None,
) -> IngestionPipeline:
    """Create an advanced pipeline with metadata extraction."""
    
    embed_model = OpenAIEmbedding(
        model=settings.embedding_model,
        api_key=settings.openai_api_key.get_secret_value(),
    )
    
    return IngestionPipeline(
        transformations=[
            # 1. Chunking
            SentenceSplitter(
                chunk_size=settings.chunk_size,
                chunk_overlap=settings.chunk_overlap,
            ),
            # 2. Metadata Extraction (ОПЦИОНАЛЬНО — дорого!)
            TitleExtractor(nodes=5),
            KeywordExtractor(keywords=5),
            # 3. Embedding
            embed_model,
        ],
        vector_store=vector_store,
        cache=cache,
    )


# ═══════════════════════════════════════════════════════════════════
# Semantic Chunking Pipeline
# ═══════════════════════════════════════════════════════════════════

def create_semantic_pipeline(
    vector_store=None,
) -> IngestionPipeline:
    """Create a pipeline with semantic chunking."""
    
    embed_model = OpenAIEmbedding(
        model=settings.embedding_model,
        api_key=settings.openai_api_key.get_secret_value(),
    )
    
    return IngestionPipeline(
        transformations=[
            # Semantic splitter группирует семантически связанные предложения
            SemanticSplitterNodeParser(
                buffer_size=1,
                breakpoint_percentile_threshold=95,
                embed_model=embed_model,
            ),
            embed_model,
        ],
        vector_store=vector_store,
    )


# ═══════════════════════════════════════════════════════════════════
# Hierarchical Pipeline (Parent-Child)
# ═══════════════════════════════════════════════════════════════════

def create_hierarchical_pipeline() -> IngestionPipeline:
    """Create a hierarchical chunking pipeline."""
    
    return IngestionPipeline(
        transformations=[
            HierarchicalNodeParser.from_defaults(
                chunk_sizes=[2048, 512, 128],  # parent -> child -> leaf
            ),
            OpenAIEmbedding(
                model=settings.embedding_model,
                api_key=settings.openai_api_key.get_secret_value(),
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════
# Запуск Pipeline
# ═══════════════════════════════════════════════════════════════════

def run_ingestion(
    documents: list[Document],
    pipeline: IngestionPipeline,
    show_progress: bool = True,
):
    """Run ingestion pipeline on documents."""
    
    nodes = pipeline.run(
        documents=documents,
        show_progress=show_progress,
    )
    
    return nodes
```

### Custom Transformations

```python
# src/ingestion/transformations.py

from typing import List, Sequence
from llama_index.core.schema import BaseNode, TransformComponent


class TextCleaner(TransformComponent):
    """Clean and normalize text in nodes."""
    
    def __call__(
        self,
        nodes: Sequence[BaseNode],
        **kwargs,
    ) -> List[BaseNode]:
        for node in nodes:
            # Убираем лишние пробелы
            text = node.get_content()
            text = " ".join(text.split())
            
            # Убираем специальные символы если нужно
            # text = text.replace("\x00", "")
            
            node.set_content(text)
        
        return list(nodes)


class MetadataEnricher(TransformComponent):
    """Add custom metadata to nodes."""
    
    def __init__(self, source_name: str):
        self.source_name = source_name
    
    def __call__(
        self,
        nodes: Sequence[BaseNode],
        **kwargs,
    ) -> List[BaseNode]:
        for node in nodes:
            node.metadata["source"] = self.source_name
            node.metadata["char_count"] = len(node.get_content())
        
        return list(nodes)
```

---

## 🗄️ VECTOR STORES

### Qdrant Setup

```python
# src/indexing/vector_store.py

from qdrant_client import QdrantClient
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.vector_stores.chroma import ChromaVectorStore
import chromadb

from src.config.settings import settings


def get_qdrant_vector_store(
    collection_name: str | None = None,
    url: str | None = None,
) -> QdrantVectorStore:
    """Get Qdrant vector store."""
    
    client = QdrantClient(
        url=url or settings.qdrant_url,
    )
    
    return QdrantVectorStore(
        client=client,
        collection_name=collection_name or settings.qdrant_collection,
    )


def get_qdrant_memory() -> QdrantVectorStore:
    """Get in-memory Qdrant for development."""
    
    client = QdrantClient(location=":memory:")
    
    return QdrantVectorStore(
        client=client,
        collection_name="dev_collection",
    )


def get_chroma_vector_store(
    collection_name: str = "documents",
    persist_dir: str = "./chroma_db",
) -> ChromaVectorStore:
    """Get ChromaDB vector store."""
    
    client = chromadb.PersistentClient(path=persist_dir)
    collection = client.get_or_create_collection(collection_name)
    
    return ChromaVectorStore(chroma_collection=collection)
```

### Index Creation

```python
# src/indexing/index.py

from pathlib import Path

from llama_index.core import (
    VectorStoreIndex,
    StorageContext,
    load_index_from_storage,
)
from llama_index.core.schema import BaseNode

from src.config.settings import settings
from src.indexing.vector_store import get_qdrant_vector_store


def create_index_from_nodes(
    nodes: list[BaseNode],
    vector_store=None,
) -> VectorStoreIndex:
    """Create index from pre-processed nodes."""
    
    if vector_store:
        storage_context = StorageContext.from_defaults(
            vector_store=vector_store,
        )
        index = VectorStoreIndex(
            nodes=nodes,
            storage_context=storage_context,
            show_progress=True,
        )
    else:
        index = VectorStoreIndex(
            nodes=nodes,
            show_progress=True,
        )
    
    return index


def create_index_from_vector_store(
    vector_store=None,
) -> VectorStoreIndex:
    """Create index from existing vector store."""
    
    vector_store = vector_store or get_qdrant_vector_store()
    
    return VectorStoreIndex.from_vector_store(
        vector_store=vector_store,
    )


def persist_index(
    index: VectorStoreIndex,
    persist_dir: str | None = None,
) -> None:
    """Persist index to disk."""
    
    persist_dir = persist_dir or settings.storage_dir
    index.storage_context.persist(persist_dir=persist_dir)


def load_index(
    persist_dir: str | None = None,
) -> VectorStoreIndex:
    """Load index from disk."""
    
    persist_dir = persist_dir or settings.storage_dir
    
    if not Path(persist_dir).exists():
        raise FileNotFoundError(f"Index not found at {persist_dir}")
    
    storage_context = StorageContext.from_defaults(persist_dir=persist_dir)
    return load_index_from_storage(storage_context)
```

---

## 🔍 RETRIEVAL

### Retrievers

```python
# src/retrieval/retrievers.py

from llama_index.core import VectorStoreIndex
from llama_index.core.retrievers import (
    VectorIndexRetriever,
    RouterRetriever,
)
from llama_index.retrievers.bm25 import BM25Retriever
from llama_index.core.schema import NodeWithScore

from src.config.settings import settings


# ═══════════════════════════════════════════════════════════════════
# Basic Vector Retriever
# ═══════════════════════════════════════════════════════════════════

def get_vector_retriever(
    index: VectorStoreIndex,
    similarity_top_k: int | None = None,
) -> VectorIndexRetriever:
    """Get basic vector retriever."""
    
    return VectorIndexRetriever(
        index=index,
        similarity_top_k=similarity_top_k or settings.similarity_top_k,
    )


# ═══════════════════════════════════════════════════════════════════
# Hybrid Retriever (Vector + BM25)
# ═══════════════════════════════════════════════════════════════════

class HybridRetriever:
    """Combine vector and BM25 retrieval."""
    
    def __init__(
        self,
        index: VectorStoreIndex,
        nodes: list,
        vector_weight: float = 0.7,
        bm25_weight: float = 0.3,
        top_k: int = 10,
    ):
        self.vector_retriever = VectorIndexRetriever(
            index=index,
            similarity_top_k=top_k,
        )
        self.bm25_retriever = BM25Retriever.from_defaults(
            nodes=nodes,
            similarity_top_k=top_k,
        )
        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight
        self.top_k = top_k
    
    def retrieve(self, query: str) -> list[NodeWithScore]:
        """Retrieve using both methods and combine scores."""
        
        # Get results from both retrievers
        vector_results = self.vector_retriever.retrieve(query)
        bm25_results = self.bm25_retriever.retrieve(query)
        
        # Combine and normalize scores
        node_scores: dict[str, float] = {}
        node_map: dict[str, NodeWithScore] = {}
        
        # Add vector scores
        for node in vector_results:
            node_id = node.node.node_id
            node_scores[node_id] = node.score * self.vector_weight
            node_map[node_id] = node
        
        # Add BM25 scores
        for node in bm25_results:
            node_id = node.node.node_id
            if node_id in node_scores:
                node_scores[node_id] += node.score * self.bm25_weight
            else:
                node_scores[node_id] = node.score * self.bm25_weight
                node_map[node_id] = node
        
        # Sort by combined score
        sorted_nodes = sorted(
            node_scores.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:self.top_k]
        
        # Return NodeWithScore objects
        results = []
        for node_id, score in sorted_nodes:
            node_with_score = node_map[node_id]
            node_with_score.score = score
            results.append(node_with_score)
        
        return results


# ═══════════════════════════════════════════════════════════════════
# Auto-Merging Retriever (Hierarchical)
# ═══════════════════════════════════════════════════════════════════

from llama_index.core.retrievers import AutoMergingRetriever
from llama_index.core.storage.docstore import SimpleDocumentStore


def get_auto_merging_retriever(
    index: VectorStoreIndex,
    docstore: SimpleDocumentStore,
    top_k: int = 6,
) -> AutoMergingRetriever:
    """Get auto-merging retriever for hierarchical nodes."""
    
    base_retriever = index.as_retriever(similarity_top_k=top_k)
    
    return AutoMergingRetriever(
        base_retriever,
        storage_context=index.storage_context,
        simple_ratio_thresh=0.5,  # Merge if >50% of children are retrieved
    )
```

### Reranking

```python
# src/retrieval/rerankers.py

from llama_index.core.postprocessor import (
    SentenceTransformerRerank,
    LLMRerank,
    SimilarityPostprocessor,
)
from llama_index.postprocessor.cohere_rerank import CohereRerank

from src.config.settings import settings


def get_sentence_transformer_reranker(
    top_n: int | None = None,
    model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
):
    """Get sentence transformer reranker (local, fast)."""
    
    return SentenceTransformerRerank(
        model=model,
        top_n=top_n or settings.rerank_top_n,
    )


def get_cohere_reranker(
    api_key: str,
    top_n: int | None = None,
    model: str = "rerank-english-v3.0",
):
    """Get Cohere reranker (API, high quality)."""
    
    return CohereRerank(
        api_key=api_key,
        model=model,
        top_n=top_n or settings.rerank_top_n,
    )


def get_llm_reranker(
    top_n: int | None = None,
    choice_batch_size: int = 5,
):
    """Get LLM-based reranker (expensive but flexible)."""
    
    return LLMRerank(
        top_n=top_n or settings.rerank_top_n,
        choice_batch_size=choice_batch_size,
    )


def get_similarity_filter(
    similarity_cutoff: float = 0.7,
):
    """Filter nodes by similarity threshold."""
    
    return SimilarityPostprocessor(
        similarity_cutoff=similarity_cutoff,
    )
```

---

## 💬 QUERY ENGINES

### Basic Query Engine

```python
# src/generation/query_engine.py

from llama_index.core import VectorStoreIndex
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.response_synthesizers import (
    ResponseMode,
    get_response_synthesizer,
)

from src.retrieval.retrievers import get_vector_retriever
from src.retrieval.rerankers import get_sentence_transformer_reranker
from src.config.settings import settings


def create_basic_query_engine(
    index: VectorStoreIndex,
    similarity_top_k: int | None = None,
):
    """Create a basic query engine."""
    
    return index.as_query_engine(
        similarity_top_k=similarity_top_k or settings.similarity_top_k,
    )


def create_reranking_query_engine(
    index: VectorStoreIndex,
    similarity_top_k: int | None = None,
    rerank_top_n: int | None = None,
):
    """Create query engine with reranking."""
    
    retriever = get_vector_retriever(
        index=index,
        similarity_top_k=similarity_top_k or settings.similarity_top_k,
    )
    
    reranker = get_sentence_transformer_reranker(
        top_n=rerank_top_n or settings.rerank_top_n,
    )
    
    response_synthesizer = get_response_synthesizer(
        response_mode=ResponseMode.COMPACT,
    )
    
    return RetrieverQueryEngine(
        retriever=retriever,
        node_postprocessors=[reranker],
        response_synthesizer=response_synthesizer,
    )


# ═══════════════════════════════════════════════════════════════════
# Response Modes
# ═══════════════════════════════════════════════════════════════════

def create_query_engine_with_mode(
    index: VectorStoreIndex,
    response_mode: str = "compact",
):
    """
    Create query engine with specific response mode.
    
    Response modes:
    - "refine": Iterate through each node, refining answer
    - "compact": Stuff as much context as possible, then refine
    - "tree_summarize": Recursively summarize chunks
    - "simple_summarize": Simple concatenation and summarize
    - "accumulate": Synthesize answer for each node, then combine
    - "compact_accumulate": Compact + accumulate
    """
    
    mode_map = {
        "refine": ResponseMode.REFINE,
        "compact": ResponseMode.COMPACT,
        "tree_summarize": ResponseMode.TREE_SUMMARIZE,
        "simple_summarize": ResponseMode.SIMPLE_SUMMARIZE,
        "accumulate": ResponseMode.ACCUMULATE,
        "compact_accumulate": ResponseMode.COMPACT_ACCUMULATE,
    }
    
    response_synthesizer = get_response_synthesizer(
        response_mode=mode_map.get(response_mode, ResponseMode.COMPACT),
    )
    
    return index.as_query_engine(
        response_synthesizer=response_synthesizer,
    )
```

### Custom Prompts

```python
# src/generation/prompts.py

from llama_index.core import PromptTemplate
from llama_index.core.prompts import PromptType


# ═══════════════════════════════════════════════════════════════════
# QA Prompt (для ответа на вопросы)
# ═══════════════════════════════════════════════════════════════════

QA_PROMPT_TMPL = """\
Контекст ниже:
---------------------
{context_str}
---------------------

Используя ТОЛЬКО предоставленный контекст (не используй внешние знания), \
ответь на вопрос.

Если ответ не может быть найден в контексте, скажи: \
"Я не нашёл информацию по этому вопросу в предоставленных документах."

Вопрос: {query_str}

Ответ: """

QA_PROMPT = PromptTemplate(
    template=QA_PROMPT_TMPL,
    prompt_type=PromptType.QUESTION_ANSWER,
)


# ═══════════════════════════════════════════════════════════════════
# Refine Prompt (для уточнения ответа)
# ═══════════════════════════════════════════════════════════════════

REFINE_PROMPT_TMPL = """\
Исходный вопрос: {query_str}

Текущий ответ: {existing_answer}

У нас есть возможность уточнить текущий ответ (только если нужно) \
используя дополнительный контекст ниже.
------------
{context_msg}
------------

Используя новый контекст, уточни исходный ответ, чтобы он лучше \
отвечал на вопрос. Если контекст не полезен, верни исходный ответ.

Уточнённый ответ: """

REFINE_PROMPT = PromptTemplate(
    template=REFINE_PROMPT_TMPL,
    prompt_type=PromptType.REFINE,
)


# ═══════════════════════════════════════════════════════════════════
# Применение промптов
# ═══════════════════════════════════════════════════════════════════

def create_query_engine_with_prompts(
    index,
    qa_prompt: PromptTemplate = QA_PROMPT,
    refine_prompt: PromptTemplate = REFINE_PROMPT,
):
    """Create query engine with custom prompts."""
    
    query_engine = index.as_query_engine()
    
    query_engine.update_prompts({
        "response_synthesizer:text_qa_template": qa_prompt,
        "response_synthesizer:refine_template": refine_prompt,
    })
    
    return query_engine
```

---

## 📊 EVALUATION (RAGAS)

```python
# src/evaluation/metrics.py

from typing import List
from dataclasses import dataclass

from llama_index.core import VectorStoreIndex
from llama_index.core.evaluation import (
    FaithfulnessEvaluator,
    RelevancyEvaluator,
    CorrectnessEvaluator,
    BatchEvalRunner,
)


@dataclass
class EvalResult:
    """Evaluation result container."""
    faithfulness: float
    relevancy: float
    correctness: float | None = None


def evaluate_single_response(
    query: str,
    response: str,
    contexts: list[str],
    reference: str | None = None,
) -> EvalResult:
    """Evaluate a single RAG response."""
    
    faithfulness_evaluator = FaithfulnessEvaluator()
    relevancy_evaluator = RelevancyEvaluator()
    
    # Faithfulness: Is the response grounded in the context?
    faithfulness_result = faithfulness_evaluator.evaluate(
        query=query,
        response=response,
        contexts=contexts,
    )
    
    # Relevancy: Is the response relevant to the query?
    relevancy_result = relevancy_evaluator.evaluate(
        query=query,
        response=response,
    )
    
    result = EvalResult(
        faithfulness=faithfulness_result.score,
        relevancy=relevancy_result.score,
    )
    
    # Correctness: Is the response correct? (requires reference)
    if reference:
        correctness_evaluator = CorrectnessEvaluator()
        correctness_result = correctness_evaluator.evaluate(
            query=query,
            response=response,
            reference=reference,
        )
        result.correctness = correctness_result.score
    
    return result


async def evaluate_batch(
    queries: list[str],
    query_engine,
    references: list[str] | None = None,
) -> dict:
    """Batch evaluate multiple queries."""
    
    evaluators = {
        "faithfulness": FaithfulnessEvaluator(),
        "relevancy": RelevancyEvaluator(),
    }
    
    if references:
        evaluators["correctness"] = CorrectnessEvaluator()
    
    runner = BatchEvalRunner(
        evaluators=evaluators,
        workers=4,
    )
    
    results = await runner.aevaluate_queries(
        query_engine=query_engine,
        queries=queries,
    )
    
    return results


# ═══════════════════════════════════════════════════════════════════
# RAGAS Integration (если установлен ragas)
# ═══════════════════════════════════════════════════════════════════

def evaluate_with_ragas(
    questions: list[str],
    answers: list[str],
    contexts: list[list[str]],
    ground_truths: list[str] | None = None,
):
    """
    Evaluate using RAGAS metrics.
    
    pip install ragas
    """
    try:
        from ragas import evaluate
        from ragas.metrics import (
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
        )
        from datasets import Dataset
    except ImportError:
        raise ImportError("Install ragas: pip install ragas datasets")
    
    data = {
        "question": questions,
        "answer": answers,
        "contexts": contexts,
    }
    
    if ground_truths:
        data["ground_truth"] = ground_truths
    
    dataset = Dataset.from_dict(data)
    
    metrics = [faithfulness, answer_relevancy, context_precision]
    if ground_truths:
        metrics.append(context_recall)
    
    result = evaluate(dataset, metrics=metrics)
    
    return result
```

---

## 🚀 ПОЛНЫЙ ПРИМЕР

```python
# src/main.py

import asyncio
from pathlib import Path

from src.config.settings import settings
from src.config.llm_settings import configure_llama_index
from src.ingestion.loaders import load_from_directory
from src.ingestion.pipeline import create_basic_pipeline, run_ingestion
from src.indexing.vector_store import get_qdrant_memory
from src.indexing.index import create_index_from_nodes
from src.generation.query_engine import create_reranking_query_engine


async def main():
    # 1. Configure LlamaIndex
    configure_llama_index()
    
    # 2. Load documents
    print("📥 Loading documents...")
    documents = load_from_directory(settings.data_dir)
    print(f"   Loaded {len(documents)} documents")
    
    # 3. Create vector store
    vector_store = get_qdrant_memory()  # In-memory for dev
    
    # 4. Create and run ingestion pipeline
    print("⚙️ Running ingestion pipeline...")
    pipeline = create_basic_pipeline(vector_store=vector_store)
    nodes = run_ingestion(documents, pipeline)
    print(f"   Created {len(nodes)} nodes")
    
    # 5. Create index
    print("📊 Creating index...")
    index = create_index_from_nodes(nodes, vector_store=vector_store)
    
    # 6. Create query engine
    query_engine = create_reranking_query_engine(index)
    
    # 7. Query!
    print("\n🔍 Ready for queries!\n")
    
    while True:
        query = input("Query (or 'quit'): ").strip()
        if query.lower() in ("quit", "exit", "q"):
            break
        
        response = query_engine.query(query)
        
        print(f"\n📝 Answer: {response.response}\n")
        print(f"📚 Sources: {len(response.source_nodes)} nodes used\n")


if __name__ == "__main__":
    asyncio.run(main())
```

---

## ✅ ЧЕКЛИСТ

```
INGESTION
□ IngestionPipeline настроен
□ Chunk size 400-800 tokens
□ Overlap 10-20%
□ Metadata extraction (title, keywords)
□ Caching для embeddings

RETRIEVAL
□ Similarity top_k = 10-20
□ Hybrid search (vector + BM25)
□ Reranking (Cohere или sentence-transformers)
□ Rerank top_n = 3-5

GENERATION
□ Custom prompts на нужном языке
□ Response mode = compact или refine
□ Streaming для длинных ответов

EVALUATION
□ Faithfulness > 0.8
□ Relevancy > 0.8
□ Context precision tracked
□ A/B тесты при изменениях

PRODUCTION
□ Persistent vector store (Qdrant, Pinecone)
□ Redis cache для embeddings
□ Async где возможно
□ Error handling
□ Logging
```

---

## 🚀 БЫСТРЫЙ ПРОМПТ ДЛЯ CLAUDE CODE

```
RAG система на LlamaIndex. Следуй docs.llamaindex.ai:

INGESTION:
- IngestionPipeline с transformations
- SentenceSplitter(chunk_size=512, chunk_overlap=50)
- OpenAIEmbedding в конце pipeline
- TitleExtractor, KeywordExtractor для metadata

VECTOR STORE:
- Qdrant или ChromaDB для dev
- Pinecone для production
- VectorStoreIndex.from_vector_store()

RETRIEVAL:
- VectorIndexRetriever(similarity_top_k=10)
- BM25Retriever для hybrid search
- SentenceTransformerRerank(top_n=5)

QUERY ENGINE:
- RetrieverQueryEngine с node_postprocessors
- ResponseMode.COMPACT
- Custom PromptTemplate для QA

ОБЯЗАТЕЛЬНО:
✅ Settings через Pydantic
✅ Persist/load index
✅ Evaluation metrics (faithfulness, relevancy)

CHUNK SIZE GUIDE:
- Prose/документы: 400-800 tokens
- Код: 80-160 tokens
- Overlap: 10-20% от chunk_size
```

---

**Версия:** 1.0  
**Дата:** 01.12.2025  
**Референс:** LlamaIndex documentation (docs.llamaindex.ai)
