# schedule/signals.py
"""
Signal simple: Crear evento de vencimiento cuando se TIMBRA factura PPD
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta
from dateutil import parser as date_parser
from Comprobantes.models import ComprobanteIngreso, EstadoCFDI
from schedule.models import Event, Calendar
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=ComprobanteIngreso)
def crear_evento_vencimiento_factura_ppd(sender, instance, created, **kwargs):
    """
    Cuando se TIMBRA una factura PPD (tiene UUID), crear evento de vencimiento
    """
    # Evitar recursión con flag temporal
    if getattr(instance, '_evento_creado', False):
        return
    
    # Solo facturas PPD
    if instance.metodo_pago != 'PPD':
        return
    
    # Solo si tiene UUID (ya está timbrada)
    if not instance.uuid:
        logger.debug(f"Factura {instance.serie}{instance.folio} sin UUID, omitiendo evento")
        return
    
    try:
        # Marcar como procesado ANTES de hacer cualquier cosa
        instance._evento_creado = True
        
        # Buscar calendario de la empresa
        calendario = Calendar.objects.filter(empresa__emisor_rfc=instance.emisor).first()
        
        if not calendario:
            logger.info(f"No hay calendario para {instance.emisor}, omitiendo evento")
            return
        
        # Buscar si ya existe evento para este UUID (identificador único e inmutable)
        evento_existente = Event.objects.filter(
            calendar=calendario,
            description__contains=f"UUID: {instance.uuid[:8]}"
        ).first()
        
        if evento_existente:
            logger.debug(f"⏭️  Evento ya existe para UUID {instance.uuid[:8]}")
            return
        
        # Calcular fecha de vencimiento
        dias_credito = instance.dias_credito or 30
        
        # Parsear fecha_timbre (formato SAT: "2024-12-03T10:30:45")
        if instance.fecha_timbre:
            fecha_base = date_parser.parse(instance.fecha_timbre)
        else:
            fecha_base = instance.fecha_creacion
        
        fecha_vencimiento = fecha_base.date() + timedelta(days=dias_credito)
        
        # Determinar color según días para vencer
        dias_para_vencer = (fecha_vencimiento - timezone.now().date()).days
        if dias_para_vencer < 0:
            color = '#ef4444'  # Rojo - vencido
        elif dias_para_vencer <= 7:
            color = '#ef4444'  # Rojo - urgente
        elif dias_para_vencer <= 15:
            color = '#f59e0b'  # Ámbar - próximo
        else:
            color = '#10b981'  # Verde - ok
        
        # Crear evento
        Event.objects.create(
            calendar=calendario,
            title=f"💰 Vencimiento: {instance.receptor_nombre} - {instance.serie}{instance.folio}",
            description=f"""
🧾 Factura: {instance.serie}{instance.folio}
👤 Cliente: {instance.receptor_nombre}
💵 Total: ${instance.total:,.2f} {instance.moneda}
📅 Emisión: {fecha_base.strftime('%d/%m/%Y')}
⏰ Vence en: {dias_para_vencer} días
🔖 UUID: {instance.uuid[:8]}...
            """.strip(),
            start=timezone.make_aware(
                timezone.datetime.combine(fecha_vencimiento, timezone.datetime.min.time().replace(hour=8))
            ),
            end=timezone.make_aware(
                timezone.datetime.combine(fecha_vencimiento, timezone.datetime.min.time().replace(hour=9))
            ),
            color_event=color,
            creator=instance.usuario_creador
        )
        
        logger.info(f"✅ Evento creado: {instance.serie}{instance.folio} - Vence: {fecha_vencimiento}")
        
    except Exception as e:
        logger.error(f"❌ Error creando evento para {instance.serie}{instance.folio}: {e}")
        
    except Exception as e:
        logger.error(f"❌ Error creando evento para {instance.serie}{instance.folio}: {e}")