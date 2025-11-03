import uuid
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone
from django.db import transaction

from myprofile.models import Extradition, TrackCode, Notification, Receipt, ExtraditionPackage


@login_required(login_url='login')
def extradition_view(request):
    """
    Оформление выдачи посылок пользователю (оператором).
    Вместо привязки track_codes к Extradition — создаём ExtraditionPackage
    для каждого трека и генерируем штрих-код.
    После оформления — треки получают статус 'claimed'.
    """

    if request.method == 'POST':
        track_codes_raw = request.POST.get('track_codes', '').strip()
        pickup_point = request.POST.get('pickup_point', '').strip()
        comment = request.POST.get('comment', '').strip()
        receipt_id = request.POST.get('receipt_id', '').strip()

        # Проверка обязательных полей
        if not track_codes_raw or not pickup_point:
            messages.error(request, "Введите трек-коды и пункт выдачи.")
            return redirect('extradition')

        track_codes_list = [line.strip() for line in track_codes_raw.splitlines() if line.strip()]

        # Атомарная транзакция: либо всё успешно, либо откат
        with transaction.atomic():
            # Создаём выдачу
            extradition = Extradition.objects.create(
                user=request.user,
                issued_by=request.user,
                pickup_point=pickup_point,
                comment=comment,
                confirmed=True  # при необходимости поменяйте на False
            )

            # Привязка чека (если указан)
            if receipt_id:
                try:
                    receipt = Receipt.objects.get(id=receipt_id)
                    extradition.receipt = receipt
                    extradition.save()
                except Receipt.DoesNotExist:
                    messages.warning(request, f"Чек с ID {receipt_id} не найден.")

            success, errors = 0, 0

            for code in track_codes_list:
                try:
                    track = TrackCode.objects.get(track_code=code)

                    # Генерация уникального штрих-кода (barcode)
                    # Формат: EPYYYYMMDD-HHMMSS-<12hex>
                    ts = timezone.now().strftime('%Y%m%d%H%M%S')
                    barcode = f"EP{ts}-{uuid.uuid4().hex[:12].upper()}"

                    # Создаём пакет — хранит barcode и исходный трек-код
                    package = ExtraditionPackage.objects.create(
                        extradition=extradition,
                        barcode=barcode,
                        track_code=track.track_code,
                        # можно добавить другие поля: weight, status и т.д.
                    )

                    # Обновляем статус исходного трека (если нужно)
                    track.status = 'claimed'
                    track.save()

                    success += 1

                    # Уведомление владельцу — указываем и трек, и штрих-код пакета
                    Notification.objects.create(
                        user=track.owner,
                        message=f"📦 Ваш трек {track.track_code} выдан в пункте: {pickup_point}. Штрих-код выдачи: {barcode}"
                    )

                except TrackCode.DoesNotExist:
                    errors += 1
                    messages.warning(request, f"❗ Трек-код '{code}' не найден.")
                except Exception as e:
                    # Ловим неожиданные ошибки при создании пакета
                    errors += 1
                    messages.error(request, f"Ошибка при обработке трека '{code}': {e}")

        messages.success(request, f"✅ Выдача оформлена ({success} пакетов, ошибок: {errors}).")
        return redirect('extradition')

    # GET — страница с формой
    return render(request, "extraditions.html", {
        'status_choices': TrackCode.STATUS_CHOICES
    })
