"""
API Router: Real-Time Sensor Processing

HTTP endpoint for ESP32 raw sensor data processing.

Features:
- Sub-10ms response time for local networks
- API key authentication
- Rate limiting (100 req/min per key)
- Input validation (Pydantic)
- Comprehensive error handling
- Performance monitoring

Endpoint:
    POST /api/v1/sensors/process

Flow:
    ESP32 → HTTP POST → Sensor Library → Process → HTTP Response → ESP32
"""

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from ..core.logging_config import get_logger
from ..db.repositories import ESPRepository, SensorRepository
from ..db.session import get_session
from ..sensors.library_loader import get_library_loader
from ..sensors.sensor_type_registry import normalize_sensor_type
from .dependencies import check_rate_limit, verify_api_key
from .schemas import (
    ErrorResponse,
    SensorCalibrateRequest,
    SensorCalibrateResponse,
    SensorProcessRequest,
    SensorProcessResponse,
)

logger = get_logger(__name__)

# Create router
router = APIRouter(
    prefix="/api/v1/sensors",
    tags=["sensors", "processing"],
)


@router.post(
    "/process",
    response_model=SensorProcessResponse,
    responses={
        200: {"description": "Processing successful"},
        400: {"model": ErrorResponse, "description": "Invalid request"},
        401: {"model": ErrorResponse, "description": "Authentication failed"},
        404: {"model": ErrorResponse, "description": "Sensor processor not found"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Process raw sensor data",
    description="""
    Process raw sensor data from ESP32 devices.
    
    **Real-time optimized**: <10ms response time on local network.
    
    **Authentication**: Requires X-API-Key header.
    
    **Rate limiting**: 100 requests per minute per API key.
    
    **Supported sensors**: ph, temperature, humidity, ec, moisture, pressure, co2, light, flow
    """,
)
async def process_sensor_data(
    request: SensorProcessRequest,
    api_key: Annotated[str, Depends(verify_api_key)],
    _rate_limit: Annotated[None, Depends(check_rate_limit)] = None,
) -> SensorProcessResponse:
    """
    Process raw sensor data in real-time.

    Args:
        request: Sensor processing request (validated)
        api_key: Verified API key from header
        _rate_limit: Rate limit check (dependency)

    Returns:
        Processed sensor data with value, unit, quality

    Raises:
        HTTPException: 400/404/500 on various errors
    """
    start_time = time.perf_counter()

    try:
        # Log incoming request
        logger.info(
            f"Sensor processing request: esp_id={request.esp_id}, "
            f"gpio={request.gpio}, type={request.sensor_type}, raw={request.raw_value}"
        )

        # Step 1: Normalize sensor type (e.g. "soil_moisture" → "moisture")
        normalized_type = normalize_sensor_type(request.sensor_type)

        # Step 2: Get library loader
        loader = get_library_loader()

        # Step 3: Get processor for normalized sensor type
        processor = loader.get_processor(normalized_type)

        if not processor:
            logger.error(
                f"No processor found for sensor type: {normalized_type} "
                f"(original: {request.sensor_type}). "
                f"Available: {loader.get_available_sensors()}"
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No processor found for sensor type '{normalized_type}'. "
                f"Available types: {', '.join(loader.get_available_sensors())}",
            )

        # Step 4: Process raw value
        try:
            result = processor.process(
                raw_value=request.raw_value,
                calibration=request.calibration,
                params=request.params,
            )
        except Exception as e:
            logger.error(
                f"Sensor processing failed: sensor_type={request.sensor_type}, "
                f"raw_value={request.raw_value}, error={e}",
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Processing failed: {str(e)}",
            )

        # Step 4: Calculate processing time
        processing_time_ms = (time.perf_counter() - start_time) * 1000

        # Step 5: Build response
        response = SensorProcessResponse(
            success=True,
            processed_value=result.value,
            unit=result.unit,
            quality=result.quality,
            processing_time_ms=round(processing_time_ms, 2),
            metadata=result.metadata,
        )

        # Log success
        logger.info(
            f"Sensor processing complete: esp_id={request.esp_id}, "
            f"gpio={request.gpio}, processed={result.value} {result.unit}, "
            f"quality={result.quality}, time={processing_time_ms:.2f}ms"
        )

        return response

    except HTTPException:
        # Re-raise HTTP exceptions
        raise

    except Exception as e:
        # Catch-all for unexpected errors
        logger.error(
            f"Unexpected error in sensor processing: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during processing",
        )


@router.get(
    "/types",
    summary="List available sensor types",
    description="Get list of sensor types supported by the server.",
)
async def list_sensor_types(
    api_key: Annotated[str, Depends(verify_api_key)],
) -> dict:
    """
    List available sensor processor types.

    Args:
        api_key: Verified API key

    Returns:
        List of available sensor types
    """
    loader = get_library_loader()
    available_sensors = loader.get_available_sensors()

    return {
        "sensor_types": available_sensors,
        "count": len(available_sensors),
    }


@router.get(
    "/health",
    summary="Sensor processing health check",
    description="Check if sensor processing subsystem is healthy.",
)
async def health_check() -> dict:
    """
    Health check for sensor processing subsystem.

    Returns:
        Health status and loaded processors
    """
    try:
        loader = get_library_loader()
        available_sensors = loader.get_available_sensors()

        return {
            "status": "healthy",
            "processors_loaded": len(available_sensors),
            "available_sensors": available_sensors,
        }
    except Exception as e:
        logger.error(f"Sensor processing health check failed: {e}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "error": str(e),
            },
        )


@router.post(
    "/calibrate",
    response_model=SensorCalibrateResponse,
    responses={
        200: {"description": "Calibration successful"},
        400: {"model": ErrorResponse, "description": "Invalid calibration data"},
        401: {"model": ErrorResponse, "description": "Authentication failed"},
        404: {"model": ErrorResponse, "description": "Sensor or ESP not found"},
        500: {"model": ErrorResponse, "description": "Calibration failed"},
    },
    summary="Calibrate a sensor",
    description="""
    Perform sensor calibration using reference points.
    
    **Calibration Methods:**
    - **pH**: 2-point linear (pH 4.0 + pH 7.0 buffers)
    - **EC**: 2-point linear (1413 µS/cm + 12880 µS/cm KCl buffers)
    - **Moisture**: 2-point linear (dry=0% + wet=100%)
    - **Temperature/Pressure/Humidity**: 1-point offset
    
    **Process:**
    1. Measure raw ADC values with sensor in known reference solutions
    2. Send calibration points to this endpoint
    3. Server calculates calibration parameters (slope/offset)
    4. Parameters are saved to sensor config (optional)
    5. Future readings automatically use calibration
    """,
)
async def calibrate_sensor(
    request: SensorCalibrateRequest,
    api_key: Annotated[str, Depends(verify_api_key)],
) -> SensorCalibrateResponse:
    """
    Calibrate a sensor using reference points.

    Args:
        request: Calibration request with points
        api_key: Verified API key

    Returns:
        Calibration result with calculated parameters
    """
    try:
        logger.info(
            f"Calibration request: esp_id={request.esp_id}, gpio={request.gpio}, "
            f"sensor_type={request.sensor_type}, points={len(request.calibration_points)}"
        )

        # Step 1: Normalize sensor type (e.g. "soil_moisture" → "moisture")
        normalized_type = normalize_sensor_type(request.sensor_type)

        # Step 2: Get library loader and processor
        loader = get_library_loader()
        processor = loader.get_processor(normalized_type)

        if not processor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No processor found for sensor type '{normalized_type}'. "
                f"Available: {', '.join(loader.get_available_sensors())}",
            )

        # Step 2: Convert calibration points to processor format
        calibration_points = [
            {"raw": point.raw, "reference": point.reference} for point in request.calibration_points
        ]

        # Step 3: Determine calibration method
        method = request.method
        if not method:
            # Auto-detect based on sensor type and point count
            if len(calibration_points) >= 2:
                method = "linear"
            else:
                method = "offset"

        # Step 4: Perform calibration
        try:
            calibration_result = processor.calibrate(
                calibration_points=calibration_points,
                method=method,
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Calibration failed: {str(e)}",
            )
        except Exception as e:
            logger.error(f"Calibration error: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Calibration calculation failed: {str(e)}",
            )

        # Step 5: Save to database (if requested)
        saved = False
        message = None

        if request.save_to_config:
            try:
                async for session in get_session():
                    esp_repo = ESPRepository(session)
                    sensor_repo = SensorRepository(session)

                    # Lookup ESP device
                    esp_device = await esp_repo.get_by_device_id(request.esp_id)
                    if not esp_device:
                        message = f"ESP device '{request.esp_id}' not found - calibration not saved"
                        logger.warning(message)
                    else:
                        # Update calibration in sensor config (sensor_type required for Multi-Value)
                        updated_config = await sensor_repo.update_calibration(
                            esp_id=esp_device.id,
                            gpio=request.gpio,
                            calibration_data=calibration_result,
                            sensor_type=request.sensor_type,
                        )

                        if updated_config:
                            await session.commit()
                            saved = True
                            logger.info(
                                f"Calibration saved: esp_id={request.esp_id}, "
                                f"gpio={request.gpio}, calibration={calibration_result}"
                            )
                        else:
                            message = (
                                f"Sensor config not found for GPIO {request.gpio} on "
                                f"'{request.esp_id}' - calibration calculated but not saved"
                            )
                            logger.warning(message)
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(e),
                )
            except Exception as e:
                logger.error(f"Failed to save calibration: {e}", exc_info=True)
                message = f"Calibration calculated but failed to save: {str(e)}"
        else:
            message = "Calibration calculated (save_to_config=False)"

        # Step 6: Build response
        response = SensorCalibrateResponse(
            success=True,
            calibration=calibration_result,
            sensor_type=request.sensor_type,
            method=method,
            saved=saved,
            message=message,
        )

        logger.info(
            f"Calibration complete: sensor_type={request.sensor_type}, "
            f"method={method}, saved={saved}"
        )

        return response

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Unexpected calibration error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during calibration",
        )
