"""
Schema Adapter for Existing Cosmos DB Data
Adapts our insurance agents to work with the existing healthcare claims schema
"""

# Existing Schema Mapping
COSMOS_SCHEMA_MAPPING = {
    "claims": {
        "id_field": "claimId",
        "fields": {
            "claimId": "claim_id",
            "memberId": "customer_id", 
            "category": "claim_type",
            "provider": "provider_name",
            "submitDate": "incident_date",
            "amountBilled": "estimated_amount",
            "status": "status",
            "region": "location"
        }
    },
    "artifacts": {
        "id_field": "fileId",
        "fields": {
            "claimId": "claim_id",
            "fileId": "document_id",
            "type": "document_type", 
            "uri": "document_uri",
            "hash": "document_hash"
        }
    }
}

# Sample existing claims we can test with
EXISTING_TEST_CLAIMS = [
    "OP-1001",  # Outpatient claim with CLN-ALPHA
    "OP-1002",  # Outpatient claim with CLN-BETA  
    "OP-1003"   # Outpatient claim with CLN-DENTAL
]
