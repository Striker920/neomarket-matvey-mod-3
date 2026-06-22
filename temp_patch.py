def _ticket_response(card: dict[str, Any]) -> dict[str, Any]:
    kind = 'CREATE' if card.get('json_before') is None else 'EDIT'
    return {
        'id': card['product_id'],
        'product_id': card['product_id'],
        'seller_id': card['seller_id'],
        'kind': kind,
        'status': card['status'],
        'queue_priority': card['queue_priority'],
        'json_before': card.get('json_before'),
        'json_after': card.get('json_after'),
        'blocking_reason_id': card.get('blocking_reason_id'),
        'moderator_comment': card.get('moderator_comment'),
        'field_reports': card.get('field_reports', []),
        'blocking_history': card.get('blocking_history'),
        'created_at': iso(card['date_created']),
        'updated_at': iso(card['date_updated']),
        'moderated_at': iso(card.get('date_moderation')),
    }
