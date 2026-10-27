"""Deep-model training code for the cloud runner, extracted from the study.

CNN / GRU: the TaskE_NPPAD package code exactly as shipped in the
self-contained notebook (its cells 24/26, mirrored in
nppad_advanced/pkg/notebook_code.py) — CNN1D, GRUNet, fit_net,
predict_proba, and the tuned hyperparameters from the package's
results/best_hp.json (CNN hidden=128 dropout=0.1 lr=0.001;
GRU hidden=64 dropout=0.1 lr=0.003). Seeds 0/1/2, probabilities averaged —
the package convention that produced the shipped prediction sheets.

ConvTran: the study's own implementation from nppad_advanced/run_deep.py
(Foumani et al., DMKD 2023: conv front-end + tAPE + eRPE transformer
encoder), seeds 0/1/2, probabilities averaged.
"""
import copy
import time

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.metrics import f1_score

import nppad_data as D

torch.set_num_threads(4)
N_CLASSES = D.N_CLASSES
CLASSES = D.CLASSES

# Tuned hyperparameters (package results/best_hp.json — do not retune here).
HP = {"CNN": dict(hidden=128, dropout=0.1, lr=0.001),
      "GRU": dict(hidden=64, dropout=0.1, lr=0.003)}
DEEP_SEEDS = (0, 1, 2)


# --------------------------------------------------------------------- CNN
class CNN1D(nn.Module):
    """Temporal convolutions over the variable channels; global average + max pooling over time."""
    def __init__(self, n_in, hidden=64, dropout=0.2, n_out=N_CLASSES):
        super().__init__()
        self.inp_drop = nn.Dropout(dropout / 2)
        layers, c = [], n_in
        for d in (1, 2, 4):
            layers += [nn.Conv1d(c, hidden, 3, padding=d, dilation=d), nn.BatchNorm1d(hidden), nn.ReLU()]
            c = hidden
        self.body = nn.Sequential(*layers)
        self.head = nn.Sequential(nn.Dropout(dropout), nn.Linear(2 * hidden, n_out))

    def forward(self, x):                      # x: (batch, time, vars)
        h = self.body(self.inp_drop(x).transpose(1, 2))
        return self.head(torch.cat([h.mean(-1), h.amax(-1)], 1))


class GRUNet(nn.Module):
    """Two-layer GRU, classification from the last hidden state."""
    def __init__(self, n_in, hidden=64, dropout=0.2, n_out=N_CLASSES):
        super().__init__()
        self.inp = nn.Sequential(nn.Dropout(dropout / 2), nn.Linear(n_in, hidden), nn.ReLU())
        self.rnn = nn.GRU(hidden, hidden, num_layers=2, batch_first=True, dropout=dropout)
        self.head = nn.Sequential(nn.Dropout(dropout), nn.Linear(hidden, n_out))

    def forward(self, x):
        out, _ = self.rnn(self.inp(x))
        return self.head(out[:, -1])


ARCHS = {"CNN": CNN1D, "GRU": GRUNet}


def fit_net(arch, data, seed=0, hidden=64, dropout=0.2, lr=1e-3, wd=1e-4, batch=64,
            max_epochs=300, patience=40, exclude_class=None):
    """Train with AdamW; early stopping on validation macro-F1 (ties broken by validation loss).

    exclude_class: drop one class from train and val (used for the unknown-accident extension)."""
    torch.manual_seed(seed); np.random.seed(seed)
    Xtr, ytr, _ = data["tr"]; Xva, yva, _ = data["va"]
    if exclude_class is not None:
        keep_tr, keep_va = ytr != exclude_class, yva != exclude_class
        Xtr, ytr, Xva, yva = Xtr[keep_tr], ytr[keep_tr], Xva[keep_va], yva[keep_va]
    model = ARCHS[arch](Xtr.shape[2], hidden, dropout)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=wd)
    Xt, yt = torch.tensor(Xtr), torch.tensor(ytr, dtype=torch.long)
    Xv, yv = torch.tensor(Xva), torch.tensor(yva, dtype=torch.long)
    g = torch.Generator().manual_seed(seed)
    best, best_state, bad, ep = (-1, -np.inf), None, 0, 0
    for ep in range(max_epochs):
        model.train()
        perm = torch.randperm(len(Xt), generator=g)
        for i in range(0, len(perm), batch):
            b = perm[i:i + batch]
            if len(b) < 2:
                continue
            opt.zero_grad()
            F.cross_entropy(model(Xt[b]), yt[b]).backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
        model.eval()
        with torch.no_grad():
            lv = model(Xv)
            vloss = F.cross_entropy(lv, yv).item()
            vf1 = f1_score(yva, lv.argmax(1).numpy(), average="macro", zero_division=0)
        score = (round(vf1, 4), -vloss)
        if score > best:
            best, best_state, bad = score, copy.deepcopy(model.state_dict()), 0
        else:
            bad += 1
            if bad >= patience:
                break
    model.load_state_dict(best_state)
    model.eval()
    model.info = {"val_macro_F1": best[0], "val_loss": -best[1], "epochs": ep + 1}
    return model


def predict_proba(model, X, mc_samples=0):
    X = torch.tensor(X)
    with torch.no_grad():
        if mc_samples:
            model.train()                       # MC dropout (BatchNorm uses batch stats in train mode,
            for m in model.modules():           # so put BN layers back to eval)
                if isinstance(m, nn.BatchNorm1d):
                    m.eval()
            p = torch.stack([F.softmax(model(X), 1) for _ in range(mc_samples)]).mean(0)
            model.eval()
            return p.numpy()
        return F.softmax(model(X), 1).numpy()


def train_cnn_gru(arch, data):
    """Package convention: seeds 0/1/2 with the tuned HP, probabilities averaged."""
    probs, val_f1s = [], []
    for s in DEEP_SEEDS:
        t = time.time()
        m = fit_net(arch, data, seed=s, **HP[arch])
        probs.append(predict_proba(m, data["te"][0]))
        val_f1s.append(m.info["val_macro_F1"])
        print(f"  {arch} seed {s}: val macro-F1 {m.info['val_macro_F1']:.4f} "
              f"({m.info['epochs']} epochs, {time.time() - t:.0f}s)", flush=True)
    return np.mean(probs, axis=0), float(np.mean(val_f1s))


# ---------------------------------------------------------------- ConvTran
class TAPE(nn.Module):
    """Time Absolute Position Encoding (Foumani et al.): sinusoid whose
    frequency is scaled by d_model / series length."""
    def __init__(self, d_model, max_len=512, dropout=0.1):
        super().__init__()
        self.drop = nn.Dropout(dropout)
        pe = torch.zeros(max_len, d_model)
        pos = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div = torch.exp(torch.arange(0, d_model, 2).float() * (-np.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(pos * div)
        pe[:, 1::2] = torch.cos(pos * div[: pe[:, 1::2].shape[1]])
        self.register_buffer("pe", pe)

    def forward(self, x):  # (B, T, d)
        T = x.size(1)
        scale = x.size(2) / max(T, 1)
        idx = (torch.arange(T, device=x.device) * scale).long().clamp(max=self.pe.size(0) - 1)
        return self.drop(x + self.pe[idx].unsqueeze(0))


class ERPEAttention(nn.Module):
    """Multi-head self-attention with learnable relative-position bias (eRPE)."""
    def __init__(self, d_model, n_heads, max_len=128, dropout=0.1):
        super().__init__()
        self.h, self.dk = n_heads, d_model // n_heads
        self.qkv = nn.Linear(d_model, 3 * d_model)
        self.out = nn.Linear(d_model, d_model)
        self.drop = nn.Dropout(dropout)
        self.rpe = nn.Parameter(torch.zeros(n_heads, 2 * max_len - 1))
        nn.init.normal_(self.rpe, std=0.02)
        self.max_len = max_len

    def forward(self, x):
        B, T, Dm = x.shape
        qkv = self.qkv(x).view(B, T, 3, self.h, self.dk).permute(2, 0, 3, 1, 4)
        q, k, v = qkv[0], qkv[1], qkv[2]
        att = (q @ k.transpose(-2, -1)) / np.sqrt(self.dk)
        rel = (torch.arange(T, device=x.device)[None, :] - torch.arange(T, device=x.device)[:, None]
               + self.max_len - 1).clamp(0, 2 * self.max_len - 2)
        att = att + self.rpe[:, rel].unsqueeze(0)
        att = self.drop(F.softmax(att, dim=-1))
        o = (att @ v).transpose(1, 2).reshape(B, T, Dm)
        return self.out(o)


class ConvTranNet(nn.Module):
    def __init__(self, n_in, d_model=64, n_heads=4, n_layers=2, dropout=0.2, T=60):
        super().__init__()
        self.embed = nn.Sequential(
            nn.Conv1d(n_in, d_model, 3, padding=1), nn.BatchNorm1d(d_model), nn.GELU(),
            nn.Conv1d(d_model, d_model, 3, padding=1), nn.BatchNorm1d(d_model), nn.GELU())
        self.tape = TAPE(d_model, dropout=dropout)
        layer = lambda: nn.ModuleList([
            ERPEAttention(d_model, n_heads, max_len=max(T, 2), dropout=dropout),
            nn.Sequential(nn.Linear(d_model, 4 * d_model), nn.GELU(), nn.Dropout(dropout),
                          nn.Linear(4 * d_model, d_model), nn.Dropout(dropout))])
        self.blocks = nn.ModuleList([layer() for _ in range(n_layers)])
        self.norms = nn.ModuleList([nn.ModuleList([nn.LayerNorm(d_model), nn.LayerNorm(d_model)])
                                    for _ in range(n_layers)])
        self.head = nn.Sequential(nn.Dropout(dropout), nn.Linear(d_model, N_CLASSES))

    def forward(self, x):  # (B, T, C)
        h = self.embed(x.transpose(1, 2)).transpose(1, 2)
        h = self.tape(h)
        for (att, ff), (n1, n2) in zip(self.blocks, self.norms):
            h = h + att(n1(h))
            h = h + ff(n2(h))
        return self.head(h.mean(1))


def train_convtran(d, seed, epochs=150, patience=20):
    torch.manual_seed(seed); np.random.seed(seed)
    (Xtr, ytr, _), (Xva, yva, _), (Xte, yte, _) = d["tr"], d["va"], d["te"]
    net = ConvTranNet(Xtr.shape[2], T=Xtr.shape[1])
    opt = torch.optim.AdamW(net.parameters(), lr=1e-3, weight_decay=1e-2)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    Xtr_t = torch.tensor(Xtr); ytr_t = torch.tensor(ytr)
    Xva_t = torch.tensor(Xva); Xte_t = torch.tensor(Xte)
    best_f1, best_state, bad = -1.0, None, 0
    n = len(Xtr_t)
    for ep in range(epochs):
        net.train()
        perm = torch.randperm(n)
        for i in range(0, n, 64):
            idx = perm[i:i + 64]
            opt.zero_grad()
            loss = F.cross_entropy(net(Xtr_t[idx]), ytr_t[idx])
            loss.backward(); opt.step()
        sched.step()
        net.eval()
        with torch.no_grad():
            pv = torch.cat([net(Xva_t[i:i + 256]).softmax(-1) for i in range(0, len(Xva_t), 256)])
        f1 = D.macro_f1(yva, pv.argmax(1).numpy())
        if f1 > best_f1 + 1e-4:
            best_f1, best_state, bad = f1, {k: v.clone() for k, v in net.state_dict().items()}, 0
        else:
            bad += 1
            if bad >= patience:
                break
    net.load_state_dict(best_state); net.eval()
    with torch.no_grad():
        pte = torch.cat([net(Xte_t[i:i + 256]).softmax(-1) for i in range(0, len(Xte_t), 256)]).numpy()
        pva = torch.cat([net(Xva_t[i:i + 256]).softmax(-1) for i in range(0, len(Xva_t), 256)]).numpy()
    return pte, pva, best_f1


def train_convtran_ensemble(data):
    probs, val_f1s = [], []
    for seed in DEEP_SEEDS:
        t = time.time()
        pte, _, vf1 = train_convtran(data, seed)
        probs.append(pte)
        val_f1s.append(vf1)
        print(f"  ConvTran seed {seed}: val macro-F1 {vf1:.4f} ({time.time() - t:.0f}s)", flush=True)
    return np.mean(probs, axis=0), float(np.mean(val_f1s))
