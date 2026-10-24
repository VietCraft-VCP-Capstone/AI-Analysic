from sklearn.compose import make_column_selector, make_column_transformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


def logistic():
    prep = make_column_transformer(
        (make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler()),
         make_column_selector(dtype_include="number")),
        (OneHotEncoder(handle_unknown="infrequent_if_exist", min_frequency=50),
         make_column_selector(dtype_include="category")),
    )
    return make_pipeline(prep, LogisticRegression(max_iter=3000))


def boosting():
    return HistGradientBoostingClassifier(
        learning_rate=0.05, max_iter=500, categorical_features="from_dtype", random_state=42
    )
