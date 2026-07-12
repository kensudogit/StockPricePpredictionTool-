"""Deep learning predictors: LSTM / GRU / Transformer / TFT-lite (PyTorch).

TensorFlow backends are available as optional aliases when installed.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

SEQ_LEN = 30


def _make_sequences(values: np.ndarray, seq_len: int = SEQ_LEN) -> tuple[np.ndarray, np.ndarray]:
    xs, ys = [], []
    for i in range(len(values) - seq_len):
        xs.append(values[i : i + seq_len])
        ys.append(values[i + seq_len])
    return np.array(xs, dtype=np.float32), np.array(ys, dtype=np.float32)


def _numpy_fallback(close: np.ndarray) -> dict[str, Any]:
    """EMA momentum fallback when torch is unavailable."""
    if len(close) < SEQ_LEN + 5:
        return {"error": "insufficient data"}
    rets = np.diff(close) / close[:-1]
    pred_ret = float(np.mean(rets[-5:]))
    return {
        "model": "numpy_ema_fallback",
        "predicted_return": pred_ret,
        "direction": "up" if pred_ret >= 0 else "down",
        "predicted_price": float(close[-1] * (1 + pred_ret)),
    }


def _train_torch(model_name: str, close: np.ndarray, epochs: int = 12) -> dict[str, Any]:
    import torch
    import torch.nn as nn

    mu, sigma = float(close.mean()), float(close.std() or 1.0)
    norm = ((close - mu) / sigma).astype(np.float32)
    X, y = _make_sequences(norm)
    if len(X) < 20:
        return _numpy_fallback(close)

    X_t = torch.tensor(X).unsqueeze(-1)  # [N, T, 1]
    y_t = torch.tensor(y)

    class LSTMModel(nn.Module):
        def __init__(self):
            super().__init__()
            self.rnn = nn.LSTM(1, 32, batch_first=True)
            self.fc = nn.Linear(32, 1)

        def forward(self, x):
            out, _ = self.rnn(x)
            return self.fc(out[:, -1, :]).squeeze(-1)

    class GRUModel(nn.Module):
        def __init__(self):
            super().__init__()
            self.rnn = nn.GRU(1, 32, batch_first=True)
            self.fc = nn.Linear(32, 1)

        def forward(self, x):
            out, _ = self.rnn(x)
            return self.fc(out[:, -1, :]).squeeze(-1)

    class TransformerModel(nn.Module):
        def __init__(self):
            super().__init__()
            enc_layer = nn.TransformerEncoderLayer(d_model=32, nhead=4, dim_feedforward=64, batch_first=True)
            self.proj = nn.Linear(1, 32)
            self.enc = nn.TransformerEncoder(enc_layer, num_layers=2)
            self.fc = nn.Linear(32, 1)

        def forward(self, x):
            h = self.proj(x)
            h = self.enc(h)
            return self.fc(h[:, -1, :]).squeeze(-1)

    class TFTLite(nn.Module):
        """Simplified Temporal Fusion style: gated residual + attention over time."""

        def __init__(self):
            super().__init__()
            self.proj = nn.Linear(1, 32)
            self.gate = nn.Linear(32, 32)
            self.attn = nn.MultiheadAttention(32, 4, batch_first=True)
            self.fc = nn.Linear(32, 1)

        def forward(self, x):
            h = torch.relu(self.proj(x))
            g = torch.sigmoid(self.gate(h))
            h = h * g
            a, _ = self.attn(h, h, h)
            return self.fc(a[:, -1, :]).squeeze(-1)

    models = {
        "lstm": LSTMModel,
        "gru": GRUModel,
        "transformer": TransformerModel,
        "tft": TFTLite,
    }
    net = models[model_name]()
    opt = torch.optim.Adam(net.parameters(), lr=1e-3)
    loss_fn = nn.MSELoss()
    net.train()
    for _ in range(epochs):
        opt.zero_grad()
        pred = net(X_t)
        loss = loss_fn(pred, y_t)
        loss.backward()
        opt.step()

    net.eval()
    with torch.no_grad():
        last_seq = torch.tensor(norm[-SEQ_LEN:]).unsqueeze(0).unsqueeze(-1)
        pred_norm = float(net(last_seq).item())
    pred_price = pred_norm * sigma + mu
    last = float(close[-1])
    pred_ret = (pred_price / last) - 1.0
    return {
        "model": f"torch_{model_name}",
        "predicted_return": pred_ret,
        "direction": "up" if pred_ret >= 0 else "down",
        "predicted_price": pred_price,
        "backend": "pytorch",
    }


def _train_tf(model_name: str, close: np.ndarray, epochs: int = 12) -> dict[str, Any]:
    import tensorflow as tf

    mu, sigma = float(close.mean()), float(close.std() or 1.0)
    norm = ((close - mu) / sigma).astype(np.float32)
    X, y = _make_sequences(norm)
    X = X[..., np.newaxis]
    if model_name == "lstm":
        layer = tf.keras.layers.LSTM(32)
    elif model_name == "gru":
        layer = tf.keras.layers.GRU(32)
    else:
        # simple dense over flattened sequence as TF transformer stand-in
        model = tf.keras.Sequential(
            [
                tf.keras.layers.Flatten(input_shape=(SEQ_LEN, 1)),
                tf.keras.layers.Dense(64, activation="relu"),
                tf.keras.layers.Dense(1),
            ]
        )
        model.compile(optimizer="adam", loss="mse")
        model.fit(X, y, epochs=epochs, verbose=0)
        pred_norm = float(model.predict(norm[-SEQ_LEN:][np.newaxis, :, np.newaxis], verbose=0)[0][0])
        pred_price = pred_norm * sigma + mu
        last = float(close[-1])
        pred_ret = pred_price / last - 1
        return {
            "model": f"tf_{model_name}",
            "predicted_return": pred_ret,
            "direction": "up" if pred_ret >= 0 else "down",
            "predicted_price": pred_price,
            "backend": "tensorflow",
        }

    model = tf.keras.Sequential(
        [
            tf.keras.layers.Input(shape=(SEQ_LEN, 1)),
            layer,
            tf.keras.layers.Dense(1),
        ]
    )
    model.compile(optimizer="adam", loss="mse")
    model.fit(X, y, epochs=epochs, verbose=0)
    pred_norm = float(model.predict(norm[-SEQ_LEN:][np.newaxis, :, np.newaxis], verbose=0)[0][0])
    pred_price = pred_norm * sigma + mu
    last = float(close[-1])
    pred_ret = pred_price / last - 1
    return {
        "model": f"tf_{model_name}",
        "predicted_return": pred_ret,
        "direction": "up" if pred_ret >= 0 else "down",
        "predicted_price": pred_price,
        "backend": "tensorflow",
    }


class DeepLearningService:
    def predict(
        self,
        df: pd.DataFrame,
        model: str = "lstm",
        backend: str = "pytorch",
        epochs: int = 12,
    ) -> dict[str, Any]:
        close = df["close"].astype(float).values
        model = model.lower()
        if model not in {"lstm", "gru", "transformer", "tft"}:
            return {"error": f"unknown model {model}"}
        try:
            if backend == "tensorflow":
                return _train_tf("lstm" if model in {"transformer", "tft"} else model, close, epochs=epochs)
            return _train_torch(model, close, epochs=epochs)
        except ImportError:
            return _numpy_fallback(close)
        except Exception as e:
            fb = _numpy_fallback(close)
            fb["warning"] = str(e)
            return fb
