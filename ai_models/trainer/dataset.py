"""
HireSense AI — Dataset Loader
Supports two real datasets:
  1. Kaggle UpdatedResumeDataSet (>500MB) — kaggle.com/datasets/gauravduttakiit/resume-dataset
  2. HuggingFace ahmedheakl/resume-atlas — no credentials needed

The dataset is used to:
  - Train a binary classifier: does this resume match this job category?
  - Extract vocabulary for TF-IDF feature engineering
"""

import os
import re
import json
import logging
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Tuple, List, Optional

import torch
from torch.utils.data import Dataset, DataLoader
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
import joblib

logger = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data"))
MODEL_DIR = Path(os.environ.get("MODEL_DIR", "/app/models"))

# ── Job category → required skill mapping (augments dataset) ────────────────
JOB_SKILL_TAXONOMY = {
    "Data Science": ["python", "machine learning", "tensorflow", "pytorch", "pandas", "numpy",
                     "statistics", "sql", "deep learning", "nlp", "computer vision"],
    "Software Engineer": ["java", "python", "c++", "algorithms", "data structures", "git",
                          "rest api", "microservices", "docker", "kubernetes"],
    "DevOps Engineer": ["docker", "kubernetes", "ci/cd", "jenkins", "terraform", "ansible",
                        "linux", "bash", "aws", "monitoring"],
    "Data Engineer": ["python", "sql", "apache spark", "hadoop", "airflow", "kafka",
                      "etl", "data pipeline", "aws", "databricks"],
    "Frontend Developer": ["react", "javascript", "typescript", "html", "css", "webpack",
                           "graphql", "responsive design", "vue.js"],
    "Backend Developer": ["python", "java", "node.js", "sql", "nosql", "rest api",
                          "microservices", "docker", "message queues"],
    "ML Engineer": ["python", "pytorch", "tensorflow", "mlops", "kubernetes", "docker",
                    "model deployment", "ci/cd", "feature engineering"],
    "Product Manager": ["agile", "scrum", "roadmap", "stakeholder management", "analytics",
                        "user research", "jira", "product strategy"],
    "HR Manager": ["recruitment", "talent acquisition", "employee relations", "hris",
                   "performance management", "onboarding", "labor law"],
    "Sales": ["crm", "salesforce", "lead generation", "negotiation", "cold calling",
              "pipeline management", "communication"],
}


def clean_text(text: str) -> str:
    """Normalize raw resume/job text."""
    if not isinstance(text, str):
        return ""
    text = text.lower()
    text = re.sub(r"http\S+|www\S+", "", text)        # Remove URLs
    text = re.sub(r"[^\w\s]", " ", text)              # Remove punctuation
    text = re.sub(r"\s+", " ", text).strip()           # Normalize whitespace
    return text


def extract_skills_from_text(text: str, skill_vocabulary: List[str]) -> List[str]:
    """Extract skills from text using vocabulary matching."""
    text_lower = text.lower()
    return [skill for skill in skill_vocabulary if skill.lower() in text_lower]


class ResumeDatasetLoader:
    """Loads and prepares the resume dataset for training."""

    def __init__(self, source: str = "huggingface"):
        self.source = source
        self.df: Optional[pd.DataFrame] = None
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.label_encoder: Optional[LabelEncoder] = None

    def load_huggingface(self) -> pd.DataFrame:
        """Load resume dataset from HuggingFace (no credentials needed)."""
        logger.info("Loading dataset from HuggingFace: ahmedheakl/resume-atlas")
        from datasets import load_dataset

        ds = load_dataset("ahmedheakl/resume-atlas", trust_remote_code=True)
        df = pd.DataFrame(ds["train"])

        # Standardize columns
        if "Resume_str" in df.columns:
            df = df.rename(columns={"Resume_str": "resume_text", "Category": "category"})
        elif "text" in df.columns:
            df = df.rename(columns={"text": "resume_text", "label": "category"})

        logger.info(f"Loaded {len(df)} resumes, categories: {df['category'].nunique()}")
        return df

    def load_kaggle(self) -> pd.DataFrame:
        """Load resume dataset from Kaggle."""
        kaggle_path = DATA_DIR / "UpdatedResumeDataSet.csv"
        if not kaggle_path.exists():
            logger.warning("Kaggle dataset not found. Falling back to HuggingFace.")
            return self.load_huggingface()

        logger.info(f"Loading Kaggle dataset from {kaggle_path}")
        df = pd.read_csv(kaggle_path)
        df = df.rename(columns={"Resume": "resume_text", "Category": "category"})
        logger.info(f"Loaded {len(df)} resumes from Kaggle")
        return df

    def load(self) -> pd.DataFrame:
        """Load dataset based on configured source."""
        if self.source == "kaggle":
            self.df = self.load_kaggle()
        else:
            self.df = self.load_huggingface()

        # Clean
        self.df["resume_text"] = self.df["resume_text"].apply(clean_text)
        self.df = self.df.dropna(subset=["resume_text", "category"])
        self.df = self.df[self.df["resume_text"].str.len() > 100]

        logger.info(f"After cleaning: {len(self.df)} samples")
        return self.df

    def build_features(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        Build TF-IDF feature matrix + encode labels.
        Returns: (X, y) arrays.
        """
        if self.df is None:
            self.load()

        # TF-IDF features (top 5000 terms, bigrams)
        self.vectorizer = TfidfVectorizer(
            max_features=5000,
            ngram_range=(1, 2),
            sublinear_tf=True,
            min_df=2,
            max_df=0.95,
        )
        X = self.vectorizer.fit_transform(self.df["resume_text"]).toarray().astype(np.float32)

        # Encode category labels
        self.label_encoder = LabelEncoder()
        y = self.label_encoder.fit_transform(self.df["category"]).astype(np.int64)

        # Save vectorizer + encoder
        MODEL_DIR.mkdir(exist_ok=True)
        joblib.dump(self.vectorizer, MODEL_DIR / "tfidf_vectorizer.pkl")
        joblib.dump(self.label_encoder, MODEL_DIR / "label_encoder.pkl")

        # Save category taxonomy
        taxonomy = {
            int(idx): name
            for idx, name in enumerate(self.label_encoder.classes_)
        }
        with open(MODEL_DIR / "category_taxonomy.json", "w") as f:
            json.dump(taxonomy, f, indent=2)

        logger.info(f"Feature matrix: {X.shape}, Classes: {len(self.label_encoder.classes_)}")
        return X, y

    def get_splits(self, test_size: float = 0.2, val_size: float = 0.1):
        """Return train/val/test splits."""
        X, y = self.build_features()
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42, stratify=y
        )
        X_train, X_val, y_train, y_val = train_test_split(
            X_train, y_train, test_size=val_size, random_state=42, stratify=y_train
        )
        return (X_train, y_train), (X_val, y_val), (X_test, y_test)


class ResumeTorchDataset(Dataset):
    """PyTorch Dataset wrapper for resume feature matrices."""

    def __init__(self, X: np.ndarray, y: np.ndarray):
        self.X = torch.tensor(X, dtype=torch.float32)
        self.y = torch.tensor(y, dtype=torch.long)

    def __len__(self) -> int:
        return len(self.y)

    def __getitem__(self, idx: int):
        return self.X[idx], self.y[idx]


def get_dataloaders(
    batch_size: int = 64,
    source: str = "huggingface",
) -> Tuple[DataLoader, DataLoader, DataLoader, int]:
    """
    Main entry point: returns (train_loader, val_loader, test_loader, num_classes).
    """
    loader = ResumeDatasetLoader(source=source)
    (X_train, y_train), (X_val, y_val), (X_test, y_test) = loader.get_splits()

    num_classes = len(np.unique(y_train))
    input_dim = X_train.shape[1]

    train_ds = ResumeTorchDataset(X_train, y_train)
    val_ds = ResumeTorchDataset(X_val, y_val)
    test_ds = ResumeTorchDataset(X_test, y_test)

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=4, pin_memory=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=2)
    test_loader = DataLoader(test_ds, batch_size=batch_size, shuffle=False, num_workers=2)

    logger.info(
        f"Dataloaders ready: train={len(train_ds)}, val={len(val_ds)}, "
        f"test={len(test_ds)}, input_dim={input_dim}, classes={num_classes}"
    )
    return train_loader, val_loader, test_loader, num_classes, input_dim
