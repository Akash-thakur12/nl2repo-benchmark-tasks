"""The model and the metric, supplied so that they are not what is being tested.

Both are deterministic: the optimiser starts from zeros, takes a fixed number of
full-batch steps at a fixed learning rate, and never samples. Two runs over the
same rows give the same number to the last bit. That matters here, because the
whole point of the exercise is that a difference in the score has exactly one
possible cause - a difference in the rows the pipeline produced.

Do not change this file. The graders import it directly.
"""
import numpy as np

STEPS = 400
LEARNING_RATE = 0.002


def fit_logistic(X, y, steps=STEPS, learning_rate=LEARNING_RATE):
    """Full-batch logistic regression from a zero start. Returns (weights, bias)."""
    X = np.asarray(X, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    if X.ndim != 2 or X.shape[0] != y.shape[0]:
        raise ValueError("X must be 2-D with one row per label")
    w = np.zeros(X.shape[1], dtype=np.float64)
    b = 0.0
    n = max(len(y), 1)
    for _ in range(steps):
        p = _sigmoid(X @ w + b)
        error = p - y
        w -= learning_rate * (X.T @ error) / n
        b -= learning_rate * float(error.sum()) / n
    return w, b


def predict_scores(X, w, b):
    """Decision values. Monotone in probability, so AUC is unaffected."""
    return np.asarray(X, dtype=np.float64) @ np.asarray(w, dtype=np.float64) + b


def roc_auc(scores, labels):
    """Area under the ROC curve, ties averaged.

    Equal scores are common here - most feature vectors are small integer counts
    and many customers share one - so ties are given their mean rank rather than
    an arbitrary order. Ignoring that makes the metric depend on sort order,
    which is exactly the kind of silent non-determinism this task is about.
    """
    scores = np.asarray(scores, dtype=np.float64)
    labels = np.asarray(labels, dtype=np.float64)
    positives = float((labels == 1).sum())
    negatives = float((labels == 0).sum())
    if positives == 0 or negatives == 0:
        raise ValueError("AUC needs at least one positive and one negative label")

    order = np.argsort(scores, kind="mergesort")
    ranked = scores[order]
    ranks = np.empty(len(scores), dtype=np.float64)
    i = 0
    while i < len(ranked):
        j = i
        while j + 1 < len(ranked) and ranked[j + 1] == ranked[i]:
            j += 1
        ranks[i:j + 1] = (i + j) / 2.0 + 1.0
        i = j + 1
    positive_rank_sum = float(ranks[labels[order] == 1].sum())
    return (positive_rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30.0, 30.0)))
