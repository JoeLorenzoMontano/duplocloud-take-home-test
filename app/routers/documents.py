"""
Document processing router.

This module provides endpoints for document processing and management.
"""

from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks, UploadFile, File, Form
from typing import List, Dict, Any, Optional
import os

from core.dependencies import (
    get_db_service,
    get_document_service,
    get_job_service
)
from core.utils import clean_filename, filter_chunks_by_filename
from models.schemas import FileUploadResponse, ChunkListResponse, ChunkInfo

router = APIRouter(tags=["documents"])

@router.post("/process", summary="Start document embedding processing in the background", 
            description="Starts processing documents in the background and returns a job ID for tracking progress.")
async def process_documents(
    background_tasks: BackgroundTasks,
    chunk_size: int = Query(None, description="Override max chunk size (chars)"),
    min_size: int = Query(None, description="Override min chunk size (chars)"),
    overlap: int = Query(None, description="Override chunk overlap (chars)"),
    enable_chunking: bool = Query(None, description="Override chunking enabled setting"),
    enhance_chunks: bool = Query(True, description="Generate additional content with Ollama to improve retrieval")
):
    """Start processing all documents in the background."""
    job_service = get_job_service()
    document_service = get_document_service()
    
    # Create a job to track progress
    job_id = job_service.create_job(
        job_type="document_processing",
        settings={
            "chunk_size": chunk_size,
            "min_size": min_size,
            "overlap": overlap,
            "enable_chunking": enable_chunking,
            "enhance_chunks": enhance_chunks
        }
    )
    
    # Add the background task
    background_tasks.add_task(
        document_service.process_documents_task,
        job_id=job_id,
        chunk_size=chunk_size,
        min_size=min_size,
        overlap=overlap,
        enable_chunking=enable_chunking,
        enhance_chunks=enhance_chunks
    )
    
    # Return the job ID and initial status
    return {
        "job_id": job_id,
        "status": "queued",
        "message": "Document processing started in background. Use /job/{job_id} to check status."
    }

@router.post("/upload-file", summary="Upload a file", 
            description="Upload a file (txt or PDF) to be processed.",
            response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    process_immediately: bool = Form(False)
):
    """Upload a file for processing."""
    document_service = get_document_service()
    job_service = get_job_service()
    
    try:
        # Check if file is empty
        contents = await file.read()
        if not contents:
            return {
                "status": "error",
                "message": "File is empty",
                "file_path": ""
            }
        
        # Reset file position after reading
        await file.seek(0)
        
        # Check file type
        if not (file.filename.endswith('.txt') or file.filename.endswith('.pdf')):
            return {
                "status": "error",
                "message": "Only .txt and .pdf files are supported",
                "file_path": ""
            }
        
        # Process the file
        file_path = document_service.upload_file(contents, file.filename)
        
        result = {
            "status": "success",
            "message": f"File uploaded successfully: {file.filename}",
            "file_path": file_path
        }
        
        # Process the file immediately if requested
        if process_immediately and background_tasks:
            # Create a job to track progress
            job_id = job_service.create_job(
                job_type="file_processing",
                settings={
                    "file_path": file_path
                }
            )
            
            # Add the background task
            background_tasks.add_task(
                document_service.process_single_file_task,
                job_id=job_id,
                file_path=file_path
            )
            
            # Add job information to the result
            result["job_id"] = job_id
            result["processing_status"] = "queued"
            result["message"] += " and queued for processing"
        
        return result
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error uploading file: {str(e)}",
            "file_path": ""
        }

@router.post("/clear-db", summary="Clear the database", description="Clear all documents from ChromaDB.")
async def clear_database():
    """Clear all documents from the database."""
    db_service = get_db_service()
    query_classifier_service = get_document_service().query_classifier
    
    try:
        # Get current document count for reporting
        doc_count = db_service.get_document_count()
        
        # Delete all documents
        db_service.delete_all_documents()
        
        # Refresh the domain terms to reflect the empty database
        try:
            query_classifier_service.update_terms_from_db(db_service.collection)
        except Exception as e:
            print(f"Error refreshing domain terms after clearing DB: {e}")
        
        return {
            "status": "success",
            "message": f"Database cleared successfully. Removed {doc_count} documents.",
            "documents_removed": doc_count
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error clearing database: {str(e)}"
        }

@router.get("/chunks", summary="List document chunks", 
          description="Retrieve chunks stored in ChromaDB with optional filtering.",
          response_model=ChunkListResponse)
async def list_document_chunks(
    limit: int = Query(20, description="Limit the number of chunks returned"),
    offset: int = Query(0, description="Starting offset for pagination"),
    filename: str = Query(None, description="Filter by filename (partial match)"),
    content: str = Query(None, description="Filter by content (partial match)")
):
    """List document chunks with optional filtering."""
    db_service = get_db_service()
    
    try:
        # Get collection count to verify it's accessible
        doc_count = db_service.get_document_count()
        if doc_count == 0:
            return {
                "status": "empty",
                "message": "No documents in the database",
                "chunks": [],
                "total_in_db": 0,
                "total_matching": 0,
                "chunks_returned": 0
            }
            
        # Get all chunks since we'll filter client-side
        query_limit = limit if not filename and not content else doc_count
        query_offset = offset if not filename and not content else 0
            
        # Get results from ChromaDB
        results = db_service.get_all_documents(include_embeddings=True)
        
        # Extract the results
        chunks = []
        for i, doc in enumerate(results["documents"]):
            metadata = results["metadatas"][i] if "metadatas" in results else {}
            embedding_dim = len(results["embeddings"][i]) if "embeddings" in results else 0
            file_name = metadata.get("filename", "unknown")
            
            # Extract original text if it exists
            original_text = metadata.get("original_text", doc)
            
            # Get enrichment if it exists
            enrichment = metadata.get("enrichment", "")
            has_enrichment = metadata.get("has_enrichment", False)
            
            chunks.append(ChunkInfo(
                id=results["ids"][i],
                text=original_text,
                filename=file_name,
                has_enrichment=has_enrichment,
                enrichment=enrichment if has_enrichment else "",
                embedding_dimension=embedding_dim
            ))
        
        # Apply filters
        filtered_chunks = filter_chunks_by_filename(chunks, filename, content)
        
        # Apply pagination
        start_idx = min(offset, len(filtered_chunks))
        end_idx = min(start_idx + limit, len(filtered_chunks))
        paginated_chunks = filtered_chunks[start_idx:end_idx]
        
        # Return the results
        return {
            "status": "success",
            "total_in_db": doc_count,
            "total_matching": len(filtered_chunks),
            "chunks_returned": len(paginated_chunks),
            "chunks": paginated_chunks
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error retrieving chunks: {str(e)}",
            "chunks": [],
            "total_in_db": 0,
            "total_matching": 0,
            "chunks_returned": 0
        }