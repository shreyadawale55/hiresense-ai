"""
HireSense AI — PyTorch Training Script (CUDA-aware, AMP, Early Stopping)
Usage: python -m trainer.train --source huggingface --epochs 30
"""

import os, json, time, logging, argparse
from pathlib import Path
import torch, torch.nn as nn, torch.optim as optim
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.cuda.amp import GradScaler, autocast
from sklearn.metrics import classification_report
import matplotlib.pyplot as plt

from trainer.dataset import get_dataloaders
from trainer.model import ResumeScorerNet

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)
MODEL_DIR = Path(os.environ.get("MODEL_DIR", "/app/models"))


class Trainer:
    def __init__(self, model, train_loader, val_loader, test_loader, device, lr=3e-4, epochs=30, patience=7):
        self.model = model.to(device)
        self.train_loader, self.val_loader, self.test_loader = train_loader, val_loader, test_loader
        self.device, self.epochs, self.patience = device, epochs, patience
        self.criterion = nn.CrossEntropyLoss(label_smoothing=0.1)
        self.optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
        self.scheduler = CosineAnnealingLR(self.optimizer, T_max=epochs, eta_min=1e-6)
        self.scaler = GradScaler(enabled=device == "cuda")
        self.history = {"train_loss": [], "val_loss": [], "train_acc": [], "val_acc": []}
        self.best_val_loss = float("inf")
        self.patience_counter = 0

    def _run_epoch(self, loader, train=True):
        self.model.train(train)
        total_loss, correct, total = 0.0, 0, 0
        with torch.set_grad_enabled(train):
            for X, y in loader:
                X, y = X.to(self.device), y.to(self.device)
                if train: self.optimizer.zero_grad()
                with autocast(enabled=self.device == "cuda"):
                    logits = self.model(X)
                    loss = self.criterion(logits, y)
                if train:
                    self.scaler.scale(loss).backward()
                    self.scaler.unscale_(self.optimizer)
                    torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                    self.scaler.step(self.optimizer)
                    self.scaler.update()
                total_loss += loss.item() * X.size(0)
                correct += (logits.argmax(1) == y).sum().item()
                total += X.size(0)
        return total_loss / total, correct / total

    def train(self):
        logger.info(f"Training on {self.device} for {self.epochs} epochs")
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        for epoch in range(1, self.epochs + 1):
            t0 = time.time()
            tl, ta = self._run_epoch(self.train_loader, True)
            vl, va = self._run_epoch(self.val_loader, False)
            self.scheduler.step()
            for k, v in zip(["train_loss","val_loss","train_acc","val_acc"],[tl,vl,ta,va]):
                self.history[k].append(v)
            logger.info(f"Epoch {epoch:03d}/{self.epochs} | TL={tl:.4f} TA={ta:.4f} | VL={vl:.4f} VA={va:.4f} | {time.time()-t0:.1f}s")
            if vl < self.best_val_loss:
                self.best_val_loss = vl
                self.patience_counter = 0
                self.model.save_checkpoint(str(MODEL_DIR/"resume_scorer.pt"), {"epoch": epoch, "val_loss": vl, "val_acc": va})
                logger.info(f"  ✓ Best model saved (val_loss={vl:.4f})")
            else:
                self.patience_counter += 1
                if self.patience_counter >= self.patience:
                    logger.info("Early stopping triggered")
                    break
        self._save_curves()
        self._evaluate_test()

    def _evaluate_test(self):
        self.model.eval()
        preds, labels = [], []
        with torch.no_grad():
            for X, y in self.test_loader:
                logits = self.model(X.to(self.device))
                preds.extend(logits.argmax(1).cpu().numpy())
                labels.extend(y.numpy())
        report = classification_report(labels, preds, output_dict=True)
        logger.info(f"Test Accuracy={report['accuracy']:.4f}, Macro-F1={report['macro avg']['f1-score']:.4f}")
        with open(MODEL_DIR/"evaluation_report.json","w") as f:
            json.dump(report, f, indent=2)

    def _save_curves(self):
        fig, axes = plt.subplots(1, 2, figsize=(12, 4))
        for ax, metric, title in zip(axes, [("train_loss","val_loss"),("train_acc","val_acc")], ["Loss","Accuracy"]):
            ax.plot(self.history[metric[0]], label=f"Train {title}", color="#6366f1")
            ax.plot(self.history[metric[1]], label=f"Val {title}", color="#f43f5e")
            ax.set_title(f"{title} Curves"); ax.legend(); ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(MODEL_DIR/"training_curves.png", dpi=150, bbox_inches="tight")
        plt.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["huggingface","kaggle"], default="huggingface")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--dropout", type=float, default=0.3)
    parser.add_argument("--device", default=None)
    args = parser.parse_args()

    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"Device: {device}")
    if device == "cuda":
        logger.info(f"GPU: {torch.cuda.get_device_name(0)}, VRAM: {torch.cuda.get_device_properties(0).total_memory/1e9:.1f}GB")

    train_loader, val_loader, test_loader, num_classes, input_dim = get_dataloaders(args.batch_size, args.source)
    model = ResumeScorerNet(input_dim=input_dim, num_classes=num_classes, dropout=args.dropout)
    logger.info(f"Model params: {sum(p.numel() for p in model.parameters()):,}")
    Trainer(model, train_loader, val_loader, test_loader, device, args.lr, args.epochs).train()
    logger.info("Training complete!")

if __name__ == "__main__":
    main()
