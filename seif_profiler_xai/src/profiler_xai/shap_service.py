"""Optional SHAP TreeExplainer service; model must already be trained."""
class ShapService:
    def __init__(self, model, feature_names):
        if not feature_names: raise ValueError("feature_names cannot be empty")
        self.model=model; self.feature_names=list(feature_names); self._explainer=None
    def _get_explainer(self):
        if self._explainer is None:
            try: import shap
            except ImportError as exc: raise RuntimeError("Install optional deps with `pip install -e '.[xai]'`.") from exc
            self._explainer=shap.TreeExplainer(self.model)
        return self._explainer
    def explain_one(self, feature_values, top_k=8):
        if top_k<1: raise ValueError("top_k must be >= 1")
        missing=[f for f in self.feature_names if f not in feature_values]
        if missing: raise ValueError(f"Missing model features: {missing}")
        try: import numpy as np
        except ImportError as exc: raise RuntimeError("NumPy is required.") from exc
        row=np.asarray([[float(feature_values[f]) for f in self.feature_names]],dtype=float)
        exp=self._get_explainer()(row); values=exp.values; base=exp.base_values
        if getattr(values,"ndim",0)==3:
            matrix=values[0]; class_idx=int(np.abs(matrix).sum(axis=0).argmax())
            contributions=matrix[:,class_idx]
            base_arr=np.asarray(base).reshape(-1); base_value=float(base_arr[min(class_idx,len(base_arr)-1)])
        else:
            contributions=np.asarray(values).reshape(-1); base_value=float(np.asarray(base).reshape(-1)[0])
        order=np.argsort(np.abs(contributions))[::-1][:top_k]
        return {"base_value":base_value,"top_features":[{"feature":self.feature_names[int(i)],
          "value":float(row[0,i]),"shap_value":float(contributions[i])} for i in order],
          "note":"SHAP describes model output, not causality; verify class/output semantics."}
