from typing import List, Set
from .schema import DetectorMetrics

def compute_metrics(
    detector_name: str,
    predictions: List[Set[str]],
    ground_truths: List[Set[str]],
    relevant_codes: Set[str]
) -> DetectorMetrics:
    tp = 0
    fp = 0
    fn = 0
    tn = 0

    for pred_set, gt_set in zip(predictions, ground_truths):
        filtered_pred = pred_set.intersection(relevant_codes)
        filtered_gt = gt_set.intersection(relevant_codes)

        current_tp = len(filtered_pred.intersection(filtered_gt))
        current_fp = len(filtered_pred.difference(filtered_gt))
        current_fn = len(filtered_gt.difference(filtered_pred))

        tp += current_tp
        fp += current_fp
        fn += current_fn

        if not filtered_pred and not filtered_gt:
            tn += 1

    precision = round(tp / (tp + fp), 4) if (tp + fp) > 0 else 1.0
    recall = round(tp / (tp + fn), 4) if (tp + fn) > 0 else 1.0
    f1 = round(2 * (precision * recall) / (precision + recall), 4) if (precision + recall) > 0 else 0.0
    fpr = round(fp / (fp + tn), 4) if (fp + tn) > 0 else 0.0
    fnr = round(fn / (fn + tp), 4) if (fn + tp) > 0 else 0.0

    return DetectorMetrics(
        detector=detector_name,
        total_samples=len(predictions),
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
        precision=precision,
        recall=recall,
        f1=f1,
        fpr=fpr,
        fnr=fnr
    )
