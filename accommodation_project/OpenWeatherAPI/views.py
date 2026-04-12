from django.http import JsonResponse
from requests import HTTPError, RequestException

from OpenWeatherAPI.services.openweather_service import get_weather


def current_weather(request):
    """
    GET /api/weather/?city=Hanoi

    Returns JSON formatted by `format_weather`.
    """
    city = request.GET.get("city", "").strip()
    if not city:
        return JsonResponse(
            {"detail": "Query parameter `city` is required."},
            status=400,
        )

    try:
        payload = get_weather(city)
    except ValueError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)
    except HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 502
        safe_status = status if 400 <= status < 600 else 502
        return JsonResponse(
            {"detail": "Upstream weather provider returned an error.", "status": safe_status},
            status=502,
        )
    except RequestException:
        return JsonResponse(
            {"detail": "Unable to reach the weather provider."},
            status=502,
        )
    except RuntimeError as exc:
        return JsonResponse({"detail": str(exc)}, status=500)

    return JsonResponse(payload)
