from __future__ import annotations
import json
import logging
import time

log = logging.getLogger("alerts")


class AlertPublisher:
    """Pushes alerts to CloudWatch Logs and/or SNS. No-op unless configured."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.enabled = bool(cfg.cw_log_group or cfg.sns_topic_arn)
        self._logs = None
        self._sns = None
        self._ready = False

    def _init(self) -> None:
        import boto3
        c = self.cfg
        if c.cw_log_group:
            self._logs = boto3.client("logs", region_name=c.aws_region)
            for fn, kw in (
                (self._logs.create_log_group, {"logGroupName": c.cw_log_group}),
                (self._logs.create_log_stream,
                 {"logGroupName": c.cw_log_group, "logStreamName": c.cw_log_stream}),
            ):
                try:
                    fn(**kw)
                except self._logs.exceptions.ResourceAlreadyExistsException:
                    pass
        if c.sns_topic_arn:
            self._sns = boto3.client("sns", region_name=c.aws_region)
        self._ready = True

    def publish(self, alert: dict) -> dict:
        """Blocking; run it in a thread. Never raises."""
        if not self.enabled:
            return {}
        result = {}
        try:
            if not self._ready:
                self._init()
            body = json.dumps(alert)
            if self._logs:
                self._logs.put_log_events(
                    logGroupName=self.cfg.cw_log_group,
                    logStreamName=self.cfg.cw_log_stream,
                    logEvents=[{"timestamp": int(time.time() * 1000), "message": body}],
                )
                result["cloudwatch"] = "ok"
            if self._sns and alert["status"] == "firing":
                self._sns.publish(
                    TopicArn=self.cfg.sns_topic_arn,
                    Subject=f"[{alert['severity']}] Log anomaly detected"[:100],
                    Message=body,
                )
                result["sns"] = "ok"
        except Exception as exc:  # noqa: BLE001
            log.error("AWS publish failed: %s", exc)
            result["error"] = str(exc)
        return result
