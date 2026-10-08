"""Pipeline hook. Node type `chroma`, data.processorId = saved processor id."""

def run_chroma_node(processor_id: str, payload: dict, transaction_id: str = None, query_template: str = None):
    from .routers.chroma import run_saved
    return run_saved(processor_id, payload, transaction_id=transaction_id, query_template=query_template)
