"""Optional SHAP TreeExplainer service; model must already be trained."""
import math

class ShapService:
    def __init__(self, model, feature_names):
        if not feature_names: raise ValueError("feature_names cannot be empty")
        if len(set(feature_names)) != len(feature_names): raise ValueError("feature_names must be unique")
        self.model=model; self.feature_names=list(feature_names); self._explainer=None
    def _get_explainer(self):
        if self._explainer is None:
            try: import shap
            except ImportError as exc: raise RuntimeError("Install optional deps with `pip install -e '.[xai]'`.") from exc
            self._explainer=shap.TreeExplainer(self.model)
        return self._explainer
    def explain_one(self, feature_values, top_k=8):
        if isinstance(top_k,bool) or not isinstance(top_k,int) or top_k<1: raise ValueError("top_k must be an integer >= 1")
        missing=[f for f in self.feature_names if f not in feature_values]
        if missing: raise ValueError(f"Missing model features: {missing}")
        try: import numpy as np
        except ImportError as exc: raise RuntimeError("NumPy is required.") from exc
        try: row=np.asarray([[float(feature_values[f]) for f in self.feature_names]],dtype=float)
        except (TypeError,ValueError) as exc: raise ValueError("Model features must be numeric") from exc
        if row.shape != (1,len(self.feature_names)) or not np.isfinite(row).all(): raise ValueError("Model features must be finite numeric values")
        exp=self._get_explainer()(row); values=np.asarray(exp.values); base=np.asarray(exp.base_values)
        n=len(self.feature_names)
        if values.ndim==2 and values.shape==(1,n): contributions=values[0]; class_idx=0
        elif values.ndim==3 and values.shape[0]==1 and values.shape[1]==n and values.shape[2]>=1:
            matrix=values[0]; class_idx=int(np.abs(matrix).sum(axis=0).argmax()); contributions=matrix[:,class_idx]
        else: raise ValueError(f"Unexpected SHAP values shape {values.shape}; expected (1,{n}) or (1,{n},classes)")
        if not np.isfinite(contributions).all(): raise ValueError("SHAP contributions contain non-finite values")
        if base.size==1: base_value=float(base.reshape(-1)[0])
        elif values.ndim==3 and base.size>class_idx: base_value=float(base.reshape(-1)[class_idx])
        else: raise ValueError(f"Unexpected SHAP base_values shape {base.shape}")
        if not math.isfinite(base_value): raise ValueError("SHAP base value is non-finite")
        order=np.argsort(np.abs(contributions))[::-1][:top_k]
        return {"base_value":base_value,"top_features":[{"feature":self.feature_names[int(i)],"value":float(row[0,i]),"shap_value":float(contributions[i])} for i in order],"note":"SHAP describes model output, not causality; verify class/output semantics."}
