"""Model wrappers shared by training scripts and the prediction API."""
from __future__ import annotations

import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin, clone
from sklearn.utils.validation import check_is_fitted


class EncodedTargetClassifier(ClassifierMixin, BaseEstimator):
    """Fit an integer-target classifier while exposing human-readable classes.

    XGBoost requires class values numbered from zero. The application, however,
    expects predictions and probability keys named Low, Medium, and High. This
    wrapper preserves that API contract in saved joblib artifacts.
    """

    def __init__(self, estimator, classes=("Low", "Medium", "High")):
        self.estimator = estimator
        self.classes = classes

    def fit(self, X, y):
        self.classes_ = np.asarray(self.classes, dtype=object)
        class_to_int = {label: index for index, label in enumerate(self.classes_)}
        encoded = np.asarray([class_to_int[value] for value in y], dtype=int)
        self.estimator_ = clone(self.estimator)
        self.estimator_.fit(X, encoded)
        return self

    def predict(self, X):
        check_is_fitted(self, ("estimator_", "classes_"))
        encoded = np.asarray(self.estimator_.predict(X), dtype=int)
        return self.classes_[encoded]

    def predict_proba(self, X):
        check_is_fitted(self, ("estimator_", "classes_"))
        return self.estimator_.predict_proba(X)
