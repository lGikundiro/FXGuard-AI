import unittest

import pandas as pd
from sklearn.dummy import DummyClassifier

from backend.app.modeling import EncodedTargetClassifier
from scripts.train_multicurrency_models import candidates


class EncodedTargetClassifierTests(unittest.TestCase):
    def test_predictions_and_probability_classes_remain_human_readable(self):
        X = pd.DataFrame({"value": [0, 1, 2, 3, 4, 5]})
        y = pd.Series(["Low", "Medium", "High", "Low", "Medium", "High"])
        model = EncodedTargetClassifier(DummyClassifier(strategy="prior"))

        model.fit(X, y)

        self.assertEqual(list(model.classes_), ["Low", "Medium", "High"])
        self.assertTrue(set(model.predict(X)).issubset(set(model.classes_)))
        self.assertEqual(model.predict_proba(X).shape, (len(X), 3))

    def test_multicurrency_candidates_include_xgboost(self):
        self.assertEqual(
            set(candidates()),
            {"logistic_regression", "random_forest", "xgboost"},
        )


if __name__ == "__main__":
    unittest.main()
