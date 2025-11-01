from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db import transaction
from myprofile.models import TrackCode, ExtraditionPackage, Notification


@login_required(login_url='login')
def extradition_package_view(request):
    """
    Страница оформления пакетов выдачи:
    - показывает клиентов с готовыми треками;
    - позволяет оператору создать и оформить пакет вручную.
    """

    # --- POST: создание и оформление пакета ---
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        pickup_point = request.POST.get('pickup_point', '').strip()
        comment = request.POST.get('comment', '').strip()

        if not user_id or not pickup_point:
            messages.error(request, "⚠️ Укажите клиента и пункт выдачи.")
            return redirect('extradition_package')

        # Проверяем, есть ли готовые треки у клиента
        ready_tracks = TrackCode.objects.filter(owner_id=user_id, status='ready')
        if not ready_tracks.exists():
            messages.warning(request, "❌ У клиента нет треков, готовых к выдаче.")
            return redirect('extradition_package')

        # Создаём новый штрихкод — например, PKG-000001
        last_id = ExtraditionPackage.objects.order_by('-id').first()
        new_id = (last_id.id + 1) if last_id else 1
        barcode = f"PKG-{new_id:06d}"

        with transaction.atomic():
            package = ExtraditionPackage.objects.create(
                barcode=barcode,
                user_id=user_id,
                is_issued=True,  # сразу помечаем как выданный
                comment=comment
            )
            package.track_codes.add(*ready_tracks)

            # Меняем статус треков
            ready_tracks.update(status='claimed')

            # Создаём уведомление
            Notification.objects.create(
                user_id=user_id,
                message=f"📦 Ваши {ready_tracks.count()} трек(-ов) выданы в пункте: {pickup_point}"
            )

        messages.success(request, f"✅ Пакет {barcode} успешно оформлен и выдан ({ready_tracks.count()} треков).")
        return redirect('extradition_package')

    # --- GET: отображаем список пакетов и клиентов с готовыми треками ---
    users = (
        TrackCode.objects.filter(status='ready')
        .values('owner__id', 'owner__username')
        .distinct()
    )

    packages = (
        ExtraditionPackage.objects.all()
        .prefetch_related('track_codes', 'user')
        .order_by('-created_at')
    )

    return render(request, "extradition_package.html", {
        "users": users,
        "packages": packages,
    })
