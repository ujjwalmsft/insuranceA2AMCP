#!/usr/bin/env python3
"""
Azure Cosmos DB MCP Server

A Model Context Protocol (MCP) server implementation for Azure Cosmos DB,
providing tools for querying and exploring Cosmos DB containers.

This server enables LLMs to interact with Cosmos DB through standardized
MCP tools, supporting operations like querying, schema inspection, and
data exploration.
"""

import argparse
import json
import logging
import os
import sys
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

from azure.cosmos import CosmosClient, exceptions
# Load environment variables from .env file
load_dotenv()
from fastmcp import FastMCP
try:
    from azure.identity import DefaultAzureCredential
    AZURE_IDENTITY_AVAILABLE = True
except ImportError:
    AZURE_IDENTITY_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('cosmos-mcp-server')

# Reduce Azure SDK HTTP verbosity unless explicitly enabled
# You can override with AZURE_LOG_LEVEL (e.g., DEBUG, INFO, WARNING, ERROR, CRITICAL)
_azure_level_name = os.getenv("AZURE_LOG_LEVEL", "WARNING").upper()
_azure_level = getattr(logging, _azure_level_name, logging.WARNING)

# Set the general Azure SDK logger level
logging.getLogger("azure").setLevel(_azure_level)

# Specifically quiet the HTTP logging policy (request/response dumps)
_http_logger = logging.getLogger("azure.core.pipeline.policies.http_logging_policy")
_http_logger.setLevel(_azure_level)
_http_logger.propagate = False

# Version information
__version__ = "0.2.0"
__author__ = "Mohammed Ashfaq"
__email__ = "ash001x@gmail.com"
__license__ = "MIT"


class CosmosDBConnection:
    """Manages the connection to Azure Cosmos DB."""
    
    def __init__(self, uri: str, key: Optional[str], database: str, container: str, use_managed_identity: bool = False):
        """
        Initialize Cosmos DB connection parameters.
        
        Args:
            uri: Cosmos DB account URI
            key: Cosmos DB account key (optional if using Managed Identity)
            database: Database name
            container: Default container name
            use_managed_identity: Use Azure Managed Identity for authentication
        """
        self.uri = uri
        self.key = key
        self.database = database
        self.default_container = container
        self.use_managed_identity = use_managed_identity
        self._client = None
        self._database_client = None
    
    def get_client(self) -> CosmosClient:
        """Get or create the Cosmos DB client."""
        if not self._client:
            if self.use_managed_identity:
                if not AZURE_IDENTITY_AVAILABLE:
                    raise RuntimeError(
                        "Azure Managed Identity requested but azure-identity package not installed. "
                        "Install with: pip install azure-identity"
                    )
                credential = DefaultAzureCredential()
                self._client = CosmosClient(self.uri, credential=credential)
                logger.info("Connected to Cosmos DB using Azure Managed Identity")
            else:
                if not self.key:
                    raise RuntimeError("Access key required when not using Managed Identity")
                self._client = CosmosClient(self.uri, credential=self.key)
                logger.info("Connected to Cosmos DB using access key")
        return self._client
    
    def get_database_client(self):
        """Get or create the database client."""
        if not self._database_client:
            self._database_client = self.get_client().get_database_client(self.database)
        return self._database_client
    
    def get_container_client(self, container_name: Optional[str] = None):
        """
        Get a container client.
        
        Args:
            container_name: Name of the container, defaults to the configured container
            
        Returns:
            Container client instance
            
        Raises:
            RuntimeError: If connection parameters are missing
        """
        if not all([self.uri, self.key, self.database, self.default_container]):
            raise RuntimeError(
                "Missing Cosmos DB connection parameters. "
                "Please provide URI, key, database, and container."
            )
        
        try:
            container = container_name or self.default_container
            return self.get_database_client().get_container_client(container)
        except Exception as e:
            logger.error(f"Failed to connect to CosmosDB container: {str(e)}")
            raise


# Global connection instance
cosmos_connection = None


def initialize_server() -> FastMCP:
    """Initialize the FastMCP server with Cosmos DB tools."""
    return FastMCP(
        "Azure Cosmos DB Explorer"
    )


# Initialize MCP server
mcp = initialize_server()


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments for Cosmos DB configuration."""
    parser = argparse.ArgumentParser(
        description="Azure Cosmos DB MCP Server - Enables LLM interaction with Cosmos DB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables:
  COSMOS_URI        Cosmos DB account URI
  COSMOS_KEY        Cosmos DB account key
  COSMOS_DATABASE   Database name
  COSMOS_CONTAINER  Default container name

Example:
  python cosmos_server.py --uri https://myaccount.documents.azure.com:443/ \\
                         --key <key> --db mydb --container mycontainer
        """
    )
    
    parser.add_argument(
        "--uri",
        dest="uri",
        default=os.getenv("COSMOS_URI"),
        help="Cosmos DB URI (can also be set via COSMOS_URI env var)"
    )
    parser.add_argument(
        "--key",
        dest="key",
        default=os.getenv("COSMOS_KEY"),
        help="Cosmos DB Key (can also be set via COSMOS_KEY env var)"
    )
    parser.add_argument(
        "--db",
        dest="db",
        default=os.getenv("COSMOS_DATABASE"),
        help="Database name (can also be set via COSMOS_DATABASE env var)"
    )
    parser.add_argument(
        "--container",
        dest="container",
        default=os.getenv("COSMOS_CONTAINER"),
        help="Container name (can also be set via COSMOS_CONTAINER env var)"
    )
    parser.add_argument(
        "--use-managed-identity",
        action="store_true",
        help="Use Azure Managed Identity for authentication instead of access key"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}"
    )
    
    return parser.parse_args()


def format_query_results(items: List[Dict[str, Any]]) -> str:
    """
    Format query results for display.
    
    Args:
        items: List of documents from query
        
    Returns:
        Formatted string representation of results
    """
    if not items:
        return "No results found"
    
    result = ["Results:", "-" * 50]
    
    for i, doc in enumerate(items, 1):
        result.append(f"\nDocument {i}:")
        for key, value in doc.items():
            if isinstance(value, (dict, list)):
                value_str = json.dumps(value, indent=2)
            else:
                value_str = str(value)
            result.append(f"  {key}: {value_str}")
    
    return "\n".join(result)


@mcp.tool()
def query_cosmos(query: str) -> str:
    """
    Run an arbitrary SQL-like query on the active CosmosDB container and return formatted results.
    
    This is the primary tool for querying the data. Use SELECT queries to fetch specific records.
    Example: "SELECT * FROM c WHERE c.City = 'Miami'"
    
    Args:
        query: SQL-like query string
        
    Returns:
        Formatted query results or error message
    """
    try:
        container = cosmos_connection.get_container_client()
        items = list(container.query_items(
            query=query,
            enable_cross_partition_query=True
        ))
        return format_query_results(items)
    except exceptions.CosmosHttpResponseError as e:
        return f"Cosmos DB error: {e.status_code} - {e.message}"
    except Exception as e:
        return f"Query error: {str(e)}"


@mcp.tool()
def list_collections() -> str:
    """
    List all container (collection) names present in the current CosmosDB database.
    
    Useful for discovering available data tables.
    
    Returns:
        List of container names or error message
    """
    try:
        db_client = cosmos_connection.get_database_client()
        containers = list(db_client.list_containers())
        
        if not containers:
            return "No containers found in database"
        
        container_names = [c['id'] for c in containers]
        return "Available containers:\n" + "\n".join(f"- {name}" for name in container_names)
    except Exception as e:
        return f"Error listing containers: {str(e)}"


@mcp.tool()
def describe_container(container_name: Optional[str] = None) -> str:
    """
    Describe the schema of a container by inspecting a sample document.
    
    Outputs a flat list of top-level fields to help understand the structure.
    Useful for building queries when no schema is predefined.
    
    Args:
        container_name: Name of container to describe (optional, uses default if not provided)
        
    Returns:
        Schema description or error message
    """
    try:
        container = cosmos_connection.get_container_client(container_name)
        
        # Get a sample document
        sample_query = "SELECT * FROM c OFFSET 0 LIMIT 1"
        items = list(container.query_items(
            query=sample_query,
            enable_cross_partition_query=True
        ))
        
        if not items:
            return f"No documents found in container '{container_name or cosmos_connection.default_container}'"
        
        sample = items[0]
        
        # Build schema description
        result = [f"Schema for container '{container_name or cosmos_connection.default_container}':", "-" * 50]
        result.append("Fields:")
        
        for key, value in sample.items():
            value_type = type(value).__name__
            result.append(f"- {key} ({value_type})")
        
        return "\n".join(result)
    except Exception as e:
        return f"Error describing container: {str(e)}"


@mcp.tool()
def find_implied_links(container_name: Optional[str] = None) -> str:
    """
    Detect relationship hints in a container by analyzing field name patterns.
    
    This tool helps infer foreign-key-like fields (e.g., `user_id`, `property_fk`),
    useful for understanding relationships.
    
    Args:
        container_name: Name of container to analyze (optional)
        
    Returns:
        Detected relationship patterns or message
    """
    try:
        container = cosmos_connection.get_container_client(container_name)
        
        # Sample documents to analyze patterns
        sample_query = "SELECT * FROM c OFFSET 0 LIMIT 10"
        items = list(container.query_items(
            query=sample_query,
            enable_cross_partition_query=True
        ))
        
        if not items:
            return "No documents found to analyze"
        
        # Analyze field patterns
        relationship_hints = set()
        id_fields = set()
        
        for doc in items:
            for key in doc:
                key_lower = key.lower()
                
                # Check for common foreign key patterns
                if key_lower.endswith(('_id', 'id', '_fk', '_ref', '_key')):
                    if key_lower != 'id' and key_lower != '_id':  # Exclude document ID
                        relationship_hints.add(key)
                
                # Check for ID-like fields
                if 'id' in key_lower:
                    id_fields.add(key)
        
        # Build result
        result = ["Potential relationships detected:", "-" * 50]
        
        if relationship_hints:
            result.append("\nForeign key candidates:")
            for field in sorted(relationship_hints):
                result.append(f"- '{field}' - may reference another collection")
        
        if id_fields:
            result.append("\nID fields found:")
            for field in sorted(id_fields):
                result.append(f"- '{field}'")
        
        if not relationship_hints and not id_fields:
            return "No obvious relationship patterns detected in field names"
        
        return "\n".join(result)
    except Exception as e:
        return f"Error analyzing relationships: {str(e)}"


@mcp.tool()
def get_sample_documents(container_name: Optional[str] = None, limit: int = 5) -> str:
    """
    Retrieve a small number of sample documents from a container to preview real data.
    
    Use this to inspect actual entries and understand data content before querying.
    
    Args:
        container_name: Name of container (optional)
        limit: Number of documents to retrieve (default: 5)
        
    Returns:
        Sample documents in JSON format or error message
    """
    try:
        if limit < 1 or limit > 100:
            return "Limit must be between 1 and 100"
        
        container = cosmos_connection.get_container_client(container_name)
        query = f"SELECT * FROM c OFFSET 0 LIMIT {limit}"
        docs = list(container.query_items(
            query=query,
            enable_cross_partition_query=True
        ))
        
        if not docs:
            return "No documents found"
        
        # Format documents
        result = [f"Sample documents from '{container_name or cosmos_connection.default_container}':", "=" * 50]
        
        for i, doc in enumerate(docs, 1):
            result.append(f"\nDocument {i}:")
            result.append(json.dumps(doc, indent=2))
        
        return "\n".join(result)
    except Exception as e:
        return f"Error fetching documents: {str(e)}"


@mcp.tool()
def count_documents(container_name: Optional[str] = None) -> str:
    """
    Count the total number of documents in the specified CosmosDB container.
    
    This is useful to understand the dataset size or for sampling purposes.
    
    Args:
        container_name: Name of container (optional)
        
    Returns:
        Document count or error message
    """
    try:
        container = cosmos_connection.get_container_client(container_name)
        
        # Use COUNT query for efficiency
        count_query = "SELECT VALUE COUNT(1) FROM c"
        result = list(container.query_items(
            query=count_query,
            enable_cross_partition_query=True
        ))
        
        count = result[0] if result else 0
        container_display = container_name or cosmos_connection.default_container
        
        return f"Container '{container_display}' contains {count:,} documents"
    except Exception as e:
        return f"Error counting documents: {str(e)}"


@mcp.tool()
def get_partition_key_info(container_name: Optional[str] = None) -> str:
    """
    Get the partition key path of the CosmosDB container.
    
    Useful when you need to optimize queries or understand how data is distributed.
    
    Args:
        container_name: Name of container (optional)
        
    Returns:
        Partition key information or error message
    """
    try:
        container = cosmos_connection.get_container_client(container_name)
        properties = container.read()
        
        partition_key = properties.get('partitionKey', {})
        paths = partition_key.get('paths', [])
        kind = partition_key.get('kind', 'Hash')
        
        container_display = container_name or cosmos_connection.default_container
        
        result = [f"Partition key info for '{container_display}':", "-" * 50]
        result.append(f"Paths: {', '.join(paths) if paths else 'None'}")
        result.append(f"Kind: {kind}")
        
        return "\n".join(result)
    except Exception as e:
        return f"Error fetching partition key: {str(e)}"


@mcp.tool()
def get_indexing_policy(container_name: Optional[str] = None) -> str:
    """
    Retrieve and display the indexing policy of the CosmosDB container.
    
    Indexing policies define how queries perform; useful for optimization/debugging.
    
    Args:
        container_name: Name of container (optional)
        
    Returns:
        Indexing policy in JSON format or error message
    """
    try:
        container = cosmos_connection.get_container_client(container_name)
        properties = container.read()
        
        indexing_policy = properties.get('indexingPolicy', {})
        container_display = container_name or cosmos_connection.default_container
        
        result = [
            f"Indexing policy for '{container_display}':",
            "-" * 50,
            json.dumps(indexing_policy, indent=2)
        ]
        
        return "\n".join(result)
    except Exception as e:
        return f"Error retrieving indexing policy: {str(e)}"


@mcp.tool()
def list_distinct_values(field_name: str, container_name: Optional[str] = None) -> str:
    """
    List all unique values for a given field in the container.
    
    Helps with filter creation, cardinality checks, and data discovery.
    
    Args:
        field_name: Name of the field to get distinct values for
        container_name: Name of container (optional)
        
    Returns:
        List of distinct values or error message
    """
    try:
        container = cosmos_connection.get_container_client(container_name)
        
        # Query for distinct values
        query = f"SELECT DISTINCT VALUE c.{field_name} FROM c"
        values = list(container.query_items(
            query=query,
            enable_cross_partition_query=True
        ))
        
        if not values:
            return f"No values found for field '{field_name}'"
        
        # Format results
        container_display = container_name or cosmos_connection.default_container
        result = [
            f"Distinct values for '{field_name}' in '{container_display}':",
            f"Total unique values: {len(values)}",
            "-" * 50
        ]
        
        # Sort values for better readability (handle different types)
        try:
            sorted_values = sorted(values, key=lambda x: (type(x).__name__, x))
        except TypeError:
            sorted_values = values
        
        for value in sorted_values:
            if value is None:
                result.append("- null")
            elif isinstance(value, str):
                result.append(f"- '{value}'")
            else:
                result.append(f"- {value}")
        
        return "\n".join(result)
    except Exception as e:
        return f"Error fetching distinct values: {str(e)}"


@mcp.tool()
def put_item(containerName: str, item: dict) -> str:
    """
    Insert or update (upsert) an item in a Cosmos DB container.
    
    This tool allows writing data to Cosmos DB containers for testing scenarios.
    
    Args:
        containerName: Name of the container to write to
        item: Dictionary representing the item to insert/update
        
    Returns:
        Success message or error details
    """
    try:
        container = cosmos_connection.get_container_client(containerName)
        
        # Ensure the item has an id field
        if 'id' not in item:
            return "Error: Item must have an 'id' field"
        
        # Upsert the item
        response = container.upsert_item(item)
        
        return f"Successfully upserted item with id '{item['id']}' in container '{containerName}'"
        
    except exceptions.CosmosHttpResponseError as e:
        return f"Cosmos DB error: {e.status_code} - {e.message}"
    except Exception as e:
        return f"Error upserting item: {str(e)}"


@mcp.tool()
def delete_item(containerName: str, item_id: str, partition_key: Optional[str] = None) -> str:
    """
    Delete an item from a Cosmos DB container.
    
    Args:
        containerName: Name of the container
        item_id: ID of the item to delete
        partition_key: Partition key value (if not provided, assumes id is the partition key)
        
    Returns:
        Success message or error details
    """
    try:
        container = cosmos_connection.get_container_client(containerName)
        
        # Use item_id as partition key if not specified
        pk_value = partition_key if partition_key is not None else item_id
        
        # Delete the item
        container.delete_item(item=item_id, partition_key=pk_value)
        
        return f"Successfully deleted item with id '{item_id}' from container '{containerName}'"
        
    except exceptions.CosmosHttpResponseError as e:
        if e.status_code == 404:
            return f"Item with id '{item_id}' not found in container '{containerName}'"
        return f"Cosmos DB error: {e.status_code} - {e.message}"
    except Exception as e:
        return f"Error deleting item: {str(e)}"


@mcp.tool()
def create_container(containerName: str, partition_key_path: str = "/id") -> str:
    """
    Create a new container in the current database.
    
    Args:
        containerName: Name for the new container
        partition_key_path: Partition key path (default: "/id")
        
    Returns:
        Success message or error details
    """
    try:
        db_client = cosmos_connection.get_database_client()
        
        # Create container
        container = db_client.create_container(
            id=containerName,
            partition_key={"paths": [partition_key_path], "kind": "Hash"}
        )
        
        return f"Successfully created container '{containerName}' with partition key '{partition_key_path}'"
        
    except exceptions.CosmosResourceExistsError:
        return f"Container '{containerName}' already exists"
    except exceptions.CosmosHttpResponseError as e:
        return f"Cosmos DB error: {e.status_code} - {e.message}"
    except Exception as e:
        return f"Error creating container: {str(e)}"


def validate_connection_params(args: argparse.Namespace) -> bool:
    """
    Validate that all required connection parameters are provided.
    
    Args:
        args: Parsed command line arguments
        
    Returns:
        True if all parameters are valid, False otherwise
    """
    missing_params = []
    
    if not args.uri:
        missing_params.append("URI (--uri or COSMOS_URI)")
    
    # Key is not required if using Managed Identity
    if not args.use_managed_identity and not args.key:
        missing_params.append("Key (--key or COSMOS_KEY) - or use --use-managed-identity")
    
    if not args.db:
        missing_params.append("Database (--db or COSMOS_DATABASE)")
    if not args.container:
        missing_params.append("Container (--container or COSMOS_CONTAINER)")
    
    if missing_params:
        logger.error(f"Missing required parameters: {', '.join(missing_params)}")
        return False
    
    return True


def main():
    """Main entry point for the Cosmos DB MCP server."""
    global cosmos_connection
    
    # Parse arguments
    args = parse_arguments()
    
    # Validate connection parameters
    if not validate_connection_params(args):
        sys.exit(1)
    
    # Initialize connection
    try:
        cosmos_connection = CosmosDBConnection(
            uri=args.uri,
            key=args.key,
            database=args.db,
            container=args.container,
            use_managed_identity=args.use_managed_identity
        )
        
        # Test connection
        auth_method = "Managed Identity" if args.use_managed_identity else "Access Key"
        logger.info(f"Connecting to Cosmos DB using {auth_method} - Database: {args.db}, Container: {args.container}")
        cosmos_connection.get_container_client()
        logger.info("Successfully connected to Cosmos DB")
        
    except Exception as e:
        logger.error(f"Failed to initialize Cosmos DB connection: {str(e)}")
        sys.exit(1)
    
    # MCP streamable-http server 
    try:
        logger.info("Starting Azure Cosmos DB MCP server...")
        mcp.run(transport="streamable-http", host="127.0.0.1", port=8080)

    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        sys.exit(1)

# Start the server by python cosmos_server.py
if __name__ == "__main__":
    main()
