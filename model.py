"""
Here we code what our model is. It may include all of feature engineering.
"""
import typing as t
from functools import partial

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin, TransformerMixin
from sklearn.preprocessing import PolynomialFeatures, KBinsDiscretizer
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

import data


EstimatorConfig = t.List[t.Dict[str, t.Any]]


def build_estimator(config: EstimatorConfig):
    estimator_mapping = get_estimator_mapping()
    steps = []
    for step in config:
        name = step["name"]
        params = step["params"]
        estimator = estimator_mapping[name](**params)
        steps.append((name, estimator))
    model = Pipeline(steps)
    return model


def get_estimator_mapping():
    return {
        "random-forest-regressor": RandomForestRegressor,
        "linear-regressor": LinearRegression,
        "average-price-per-neighborhood-regressor": AveragePricePerNeighborhoodRegressor,
        "age-extractor": AgeExtractor,
        "categorical-encoder": CategoricalEncoder,
        "standard-scaler": StandardScaler,
        "discretizer": _get_discretizer,
        "crosser": _get_crosser,
        "averager": AveragePricePerNeighborhoodExtractor,
    }


def _get_discretizer(
    *,
    bins_per_column: t.Mapping[str, int],
    encode: str = "onehot",
    stratey: str = "quantile",
):
    columns, n_bins = zip(*bins_per_column.items())
    transformer = ColumnTransformer(
        [
            (
                "discretizer",
                KBinsDiscretizer(n_bins=n_bins, encode=encode, strategy=stratey),
                columns,
            )
        ],
        remainder="drop",
    )

    return transformer


def _get_crosser(
    *,
    columns: t.Sequence[int],
):
    transformer = ColumnTransformer(
        ("crosser", PolynomialFeatures(interaction_only=True), columns),
        remainder="passthrough",
    )
    return transformer


class AgeExtractor(BaseEstimator, TransformerMixin):
    def fit(self, X, y=None):
        return self

    def transform(self, X):
        X = X.copy()
        X["HouseAge"] = X["YrSold"] - X["YearBuilt"]
        X["RemodAddAge"] = X["YrSold"] - X["YearRemodAdd"]
        X["GarageAge"] = X["YrSold"] - X["GarageYrBlt"]
        return X


class CategoricalEncoder(BaseEstimator, TransformerMixin):
    def __init__(
        self,
        *,
        one_hot: bool = False,
        force_dense_array: bool = False,
        pass_through_columns: t.Optional[t.Sequence[str]] = None,
    ):
        self.one_hot = one_hot
        self.force_dense_array = force_dense_array
        self.pass_through_columns = pass_through_columns
        self.categorical_column_names = (
            data.get_binary_column_names() + data.get_categorical_column_names()
        )
        mapping = data.get_categorical_variables_values_mapping()
        self.categories = [mapping[k] for k in self.categorical_column_names]

    def fit(self, X, y=None):
        X = X.copy()
        self.n_features_in_ = X.shape[1]
        pass_through_columns = data.get_numeric_column_names()
        if self.pass_through_columns is not None:
            pass_through_columns = pass_through_columns + self.pass_through_columns
        encoder_cls = (
            partial(OneHotEncoder, drop="first", sparse=not self.force_dense_array)
            if self.one_hot
            else OrdinalEncoder
        )
        self._column_transformer = ColumnTransformer(
            transformers=[
                (
                    "encoder",
                    encoder_cls(
                        categories=self.categories,
                    ),
                    self.categorical_column_names,
                ),
                ("pass-numeric", "passthrough", pass_through_columns),
            ],
            remainder="drop",
        )
        self._column_transformer = self._column_transformer.fit(X, y=y)
        return self

    def transform(self, X):
        return self._column_transformer.transform(X)


class AveragePricePerNeighborhoodRegressor(BaseEstimator, RegressorMixin):
    def fit(self, X, y):
        """Computes the mode of the price per neighbor on training data."""
        df = pd.DataFrame({"Neighborhood": X["Neighborhood"], "price": y})
        self.means_ = df.groupby("Neighborhood").mean().to_dict()["price"]
        self.global_mean_ = y.mean()
        return self

    def predict(self, X):
        """Predicts the mode computed in the fit method."""

        def get_average(x):
            if x in self.means_:
                return self.means_[x]
            else:
                return self.global_mean_

        y_pred = X["Neighborhood"].apply(get_average)
        return y_pred


class AveragePricePerNeighborhoodExtractor(BaseEstimator, TransformerMixin):
    def fit(self, X, y):
        df = pd.DataFrame({"Neighborhood": X["Neighborhood"], "price": y})
        self.means_ = df.groupby("Neighborhood").mean().to_dict()["price"]
        self.global_mean_ = y.mean()
        return self

    def transform(self, X):
        def get_average(x):
            if x in self.means_:
                return self.means_[x]
            else:
                return self.global_mean_

        X["AveragePriceInNeihborhood"] = X["Neighborhood"].apply(get_average)
        return X
