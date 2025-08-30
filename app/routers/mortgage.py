import os
import tempfile
import shutil
import logging
from typing import List
from fastapi import APIRouter, File, UploadFile, HTTPException, Depends

from ..config import settings
from ..models import MortgageSimulationResponse, DocumentClassificationSummary, IndividualAnalysisSummary, CrossValidationResult
from ..services import DocumentAnalysisService, MortgageCalculatorService
from ..dependencies import get_document_analysis_service, get_mortgage_calculator_service


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/mortgage",
    tags=["mortgage"],
    responses={404: {"description": "Not found"}},
)


@router.post("/simulation", response_model=MortgageSimulationResponse)
async def comprehensive_mortgage_simulation(
    files: List[UploadFile] = File(...),
    document_service: DocumentAnalysisService = Depends(get_document_analysis_service),
    mortgage_service: MortgageCalculatorService = Depends(get_mortgage_calculator_service),
):
    """Comprehensive mortgage simulation using mixed financial documents."""
    
    # Validate request
    if len(files) > settings.max_files_per_request:
        raise HTTPException(
            status_code=400, 
            detail=f"Maximum {settings.max_files_per_request} documents allowed"
        )
    
    if len(files) == 0:
        raise HTTPException(status_code=400, detail="At least 1 document required")
    
    # Validate all files are PDFs
    for file in files:
        if not file.filename or not file.filename.lower().endswith('.pdf'):
            raise HTTPException(
                status_code=400, 
                detail=f"File {file.filename} is not a PDF"
            )
    
    document_analyses = []
    temp_paths = []
    
    try:
        # Process each document
        for file in files:
            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                shutil.copyfileobj(file.file, tmp_file)
                tmp_path = tmp_file.name
                temp_paths.append(tmp_path)
            
            # Analyze document
            filename = file.filename or "unknown_file.pdf"
            analysis = await document_service.analyze_document(tmp_path, filename)
            document_analyses.append(analysis)
            
            logger.info(f"Processed document: {file.filename} - Type: {analysis.document_type} - Confidence: {analysis.confidence:.2f}")
        
        # Cross-validate data between documents
        validation_results = mortgage_service.cross_validate_financial_data(document_analyses)
        
        # Create comprehensive mortgage simulation
        simulation_analysis = mortgage_service.create_comprehensive_mortgage_simulation(
            document_analyses, validation_results
        )
        
        # Format response data
        document_classifications = [
            DocumentClassificationSummary(
                filename=doc.filename,
                document_type=doc.document_type.value,
                confidence=int(doc.confidence * 100)
            )
            for doc in document_analyses
        ]
        
        individual_analyses = [
            IndividualAnalysisSummary(
                filename=doc.filename,
                document_type=doc.document_type.value,
                analysis=f"Document Type: {doc.document_type.value}\nConfidence: {doc.confidence:.1%}\nAnalysis Data: {str(doc.analysis)}"
            )
            for doc in document_analyses
        ]
        
        cross_validation = []
        if validation_results.income_consistency:
            cross_validation.append(CrossValidationResult(
                check="Income Consistency",
                status=validation_results.income_consistency.status,
                details=validation_results.income_consistency.details
            ))
        
        return MortgageSimulationResponse(
            documents_processed=len(files),
            document_classifications=document_classifications,
            individual_analyses=individual_analyses,
            cross_validation=cross_validation,
            comprehensive_mortgage_analysis=simulation_analysis
        )
        
    except Exception as e:
        logger.error(f"Mortgage simulation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")
    finally:
        # Clean up all temporary files
        for tmp_path in temp_paths:
            try:
                os.unlink(tmp_path)
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup temp file {tmp_path}: {cleanup_error}")
        
        # Close all file handles
        for file in files:
            if file.file:
                try:
                    file.file.close()
                except Exception as close_error:
                    logger.warning(f"Failed to close file handle for {file.filename}: {close_error}")