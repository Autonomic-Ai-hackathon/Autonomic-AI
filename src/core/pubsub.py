import json
from google.cloud import pubsub_v1
from ddtrace import tracer
from ddtrace.propagation.http import HTTPPropagator 
from src.config import PROJECT_ID
from concurrent.futures import TimeoutError


publisher = pubsub_v1.PublisherClient()


def publish_background_event(topic_name: str, payload: dict):
    """
    Publishes to Pub/Sub with Datadog Trace Injection.
    """
    topic_path = publisher.topic_path(PROJECT_ID, topic_name)
    data_str = json.dumps(payload).encode("utf-8")

    # INJECT TRACE ID (The Soul Transfer)
    span = tracer.current_span()
    headers = {}
    if span:
        # ✅ FIXED: Use HTTPPropagator.inject (not tracer.inject)
        HTTPPropagator.inject(span.context, headers)

    future = publisher.publish(topic_path, data_str, **headers)
    return future.result()


def listen_to_topic(subscription_name: str, callback_func):
    """
    Generic listener that extracts traces and runs the worker logic.
    """
    subscriber = pubsub_v1.SubscriberClient()
    sub_path = subscriber.subscription_path(PROJECT_ID, subscription_name)

    def wrapper(message):
        try:
            # Extract Trace ID
            headers = dict(message.attributes)
            
            # ✅ FIXED: Use HTTPPropagator.extract (not tracer.extract)
            context = HTTPPropagator.extract(headers)
            
            with tracer.start_span("worker.process", child_of=context):
                payload = json.loads(message.data.decode("utf-8"))
                callback_func(payload)
                message.ack()
        except Exception as e:
            print(f"❌ Worker Error: {e}")
            message.nack()

    streaming_pull = subscriber.subscribe(sub_path, callback=wrapper)
    with subscriber:
        try:
            streaming_pull.result()
        except TimeoutError:
            streaming_pull.cancel()
