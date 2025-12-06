import datetime
from urllib.parse import urlencode

from django import template
from django.conf import settings
from django.template.loader import get_template
from django.urls import reverse
from django.utils import timezone
from django.utils.dateformat import format
from django.utils.html import escape

from schedule.models import Calendar
from schedule.periods import weekday_abbrs, weekday_names
from schedule.settings import (
    CHECK_CALENDAR_PERM_FUNC,
    CHECK_EVENT_PERM_FUNC,
    SCHEDULER_PREVNEXT_LIMIT_SECONDS,
)

register = template.Library()

# ============================================
# TEMPLATE FILTERS PERSONALIZADOS
# ============================================

@register.filter
def minutes_since_midnight(dt):
    """
    Calcula pixeles desde el top (1 minuto = 1 pixel).
    Maneja timezone-aware datetimes correctamente.
    """
    if not dt:
        return 0
    
    # Si es timezone-aware, convertir a la zona horaria local
    if timezone.is_aware(dt):
        # Convertir a timezone local del settings
        local_dt = timezone.localtime(dt)
        return local_dt.hour * 60 + local_dt.minute
    
    # Si es naive, usar directamente
    return dt.hour * 60 + dt.minute

@register.filter  
def duration_in_minutes(start, end):
    """
    Calcula altura del evento en pixeles. Mínimo 20px para clickear.
    Maneja timezone-aware datetimes correctamente.
    """
    if not start or not end:
        return 20
    
    # Si son timezone-aware, convertir a timezone local
    if timezone.is_aware(start) and timezone.is_aware(end):
        local_start = timezone.localtime(start)
        local_end = timezone.localtime(end)
        duration = (local_end - local_start).total_seconds() / 60
    else:
        duration = (end - start).total_seconds() / 60
    
    return max(20, int(duration))

@register.filter
def get_range(n):
    """Para iterar: {% for hour in 24|get_range %}"""
    return range(int(n))

# ============================================
# TEMPLATE TAGS PERSONALIZADOS
# ============================================

@register.simple_tag
def get_day_events_with_columns(period):
    """
    Obtiene eventos del día y calcula columnas para eventos superpuestos.
    Retorna lista de dicts con: occurrence, column, total_columns
    
    IMPORTANTE: Para eventos multi-día, solo muestra la porción del día actual.
    """
    # Obtener todas las occurrences del período
    occurrences = list(period.occurrences)
    
    # Inicio y fin del día actual (sin horas)
    day_start = period.start.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + datetime.timedelta(days=1)
    
    # Ajustar occurrences multi-día para que solo muestren la porción del día actual
    adjusted_occurrences = []
    for occ in occurrences:
        # Convertir a timezone local si es necesario
        occ_start = timezone.localtime(occ.start) if timezone.is_aware(occ.start) else occ.start
        occ_end = timezone.localtime(occ.end) if timezone.is_aware(occ.end) else occ.end
        
        # Ajustar inicio si empieza antes del día actual
        adjusted_start = max(occ_start, day_start)
        
        # Ajustar fin si termina después del día actual
        adjusted_end = min(occ_end, day_end)
        
        # Crear copia con fechas ajustadas
        class AdjustedOccurrence:
            def __init__(self, original_occ, adj_start, adj_end):
                self.original = original_occ
                self.start = adj_start
                self.end = adj_end
                # Copiar todos los atributos del original
                self.title = original_occ.title
                self.description = original_occ.description
                self.event = original_occ.event
                self.cancelled = original_occ.cancelled
                self.id = original_occ.id
        
        adjusted_occurrences.append(AdjustedOccurrence(occ, adjusted_start, adjusted_end))
    
    # Ordenar por hora de inicio
    adjusted_occurrences.sort(key=lambda x: x.start)
    
    if not adjusted_occurrences:
        return []
    
    result = []
    
    # Para cada evento, calcular su grupo de superposición
    for i, occ in enumerate(adjusted_occurrences):
        # Encontrar todos los eventos que se superponen con este
        group = [i]
        
        for j, other_occ in enumerate(adjusted_occurrences):
            if i != j and (occ.start < other_occ.end and occ.end > other_occ.start):
                group.append(j)
        
        # Ordenar grupo
        group.sort()
        
        # Calcular columna dentro del grupo
        column = group.index(i)
        total_columns = len(group)
        
        result.append({
            'occurrence': occ,
            'column': column,
            'total_columns': total_columns
        })
    
    return result

@register.simple_tag
def get_day_slots(period, start_hour=8, end_hour=20, increment=30):
    """
    Genera slots de tiempo para un día con sus ocurrencias.
    Basado en _cook_slots pero retorna data en lugar de renderizar template.
    """
    tdiff = datetime.timedelta(minutes=increment)
    
    # Crear el período completo del día desde start_hour hasta end_hour
    start_time = period.start.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    
    # Si end_hour es 24, usar 23:59:59 del mismo día
    if end_hour >= 24:
        end_time = period.start.replace(hour=23, minute=59, second=59, microsecond=999999)
    else:
        end_time = period.start.replace(hour=end_hour, minute=0, second=0, microsecond=0)
    
    num = int((end_time - start_time).total_seconds()) // int(tdiff.total_seconds())
    
    slots = []
    current = start_time
    
    for i in range(num):
        slot_end = current + tdiff
        # Usar el método get_time_slot del period para obtener las ocurrencias correctas
        time_slot = period.get_time_slot(current, slot_end)
        
        slots.append({
            'start': current,
            'end': slot_end,
            'occurrences': time_slot.occurrences
        })
        current = slot_end
    
    return slots

# ============================================
# INCLUSION TAGS ORIGINALES DE DJANGO-SCHEDULER
# ============================================

@register.inclusion_tag("schedule/_month_table.html", takes_context=True)
def month_table(context, calendar, month, size="regular", shift=None):
    if shift:
        if shift == -1:
            month = month.prev()
        if shift == 1:
            month = next(month)
    if size == "small":
        context["day_names"] = weekday_abbrs
    else:
        context["day_names"] = weekday_names
    context["calendar"] = calendar
    context["month"] = month
    context["size"] = size
    return context


@register.inclusion_tag("schedule/_day_cell.html", takes_context=True)
def day_cell(context, calendar, day, month, size="regular"):
    context.update({"calendar": calendar, "day": day, "month": month, "size": size})
    return context


@register.inclusion_tag("schedule/_daily_table.html", takes_context=True)
def daily_table(context, day, start=8, end=20, increment=30):
    """
    Display a nice table with occurrences and action buttons.
    Arguments:
    start - hour at which the day starts
    end - hour at which the day ends
    increment - size of a time slot (in minutes)
    """
    user = context["request"].user
    addable = CHECK_EVENT_PERM_FUNC(None, user)
    if "calendar" in context:
        addable = addable and CHECK_CALENDAR_PERM_FUNC(context["calendar"], user)
    context["addable"] = addable
    day_part = day.get_time_slot(
        day.start + datetime.timedelta(hours=start),
        day.start + datetime.timedelta(hours=end),
    )
    # get slots to display on the left
    slots = _cook_slots(day_part, increment)
    context["slots"] = slots
    return context


@register.inclusion_tag("schedule/_event_title.html", takes_context=True)
def title(context, occurrence):
    context.update({"occurrence": occurrence})
    return context


@register.inclusion_tag("schedule/_event_options.html", takes_context=True)
def options(context, occurrence):
    context.update(
        {"occurrence": occurrence, "MEDIA_URL": getattr(settings, "MEDIA_URL")}
    )
    context["view_occurrence"] = occurrence.get_absolute_url()
    user = context["request"].user
    if CHECK_EVENT_PERM_FUNC(occurrence.event, user) and CHECK_CALENDAR_PERM_FUNC(
        occurrence.event.calendar, user
    ):
        context["edit_occurrence"] = occurrence.get_edit_url()
        context["cancel_occurrence"] = occurrence.get_cancel_url()
        context["delete_event"] = reverse("delete_event", args=(occurrence.event.id,))
        context["edit_event"] = reverse(
            "edit_event", args=(occurrence.event.calendar.slug, occurrence.event.id)
        )
    else:
        context["edit_event"] = context["delete_event"] = ""
    return context


@register.inclusion_tag("schedule/_create_event_options.html", takes_context=True)
def create_event_url(context, calendar, slot):
    context.update({"calendar": calendar, "MEDIA_URL": getattr(settings, "MEDIA_URL")})
    lookup_context = {"calendar_slug": calendar.slug}
    context["create_event_url"] = "{}{}".format(
        reverse("calendar_create_event", kwargs=lookup_context),
        querystring_for_date(slot),
    )
    return context


# ============================================
# TEMPLATE NODES
# ============================================

class CalendarNode(template.Node):
    def __init__(self, content_object, distinction, context_var, create=False):
        self.content_object = template.Variable(content_object)
        self.distinction = distinction
        self.context_var = context_var

    def render(self, context):
        Calendar.objects.get_calendar_for_object(
            self.content_object.resolve(context), self.distinction
        )
        context[self.context_var] = Calendar.objects.get_calendar_for_object(
            self.content_object.resolve(context), self.distinction
        )
        return ""


@register.tag
def get_calendar(parser, token):
    contents = token.split_contents()
    if len(contents) == 4:
        _, content_object, _, context_var = contents
        distinction = None
    elif len(contents) == 5:
        _, content_object, distinction, _, context_var = token.split_contents()
    else:
        raise template.TemplateSyntaxError(
            "%r tag follows form %r <content_object> as <context_var>"
            % (token.contents.split()[0], token.contents.split()[0])
        )
    return CalendarNode(content_object, distinction, context_var)


class CreateCalendarNode(template.Node):
    def __init__(self, content_object, distinction, context_var, name):
        self.content_object = template.Variable(content_object)
        self.distinction = distinction
        self.context_var = context_var
        self.name = name

    def render(self, context):
        context[self.context_var] = Calendar.objects.get_or_create_calendar_for_object(
            self.content_object.resolve(context), self.distinction, name=self.name
        )
        return ""


@register.tag
def get_or_create_calendar(parser, token):
    contents = token.split_contents()
    if len(contents) > 2:
        obj = contents[1]
        if "by" in contents:
            by_index = contents.index("by")
            distinction = contents[by_index + 1]
        else:
            distinction = None
        if "named" in contents:
            named_index = contents.index("named")
            name = contents[named_index + 1]
            if name[0] == name[-1]:
                name = name[1:-1]
        else:
            name = None
        if "as" in contents:
            as_index = contents.index("as")
            context_var = contents[as_index + 1]
        else:
            raise template.TemplateSyntaxError(
                "%r tag requires an a context variable: %r <content_object> [named <calendar name>] [by <distinction>] as <context_var>"
                % (token.split_contents()[0], token.split_contents()[0])
            )
    else:
        raise template.TemplateSyntaxError(
            "%r tag follows form %r <content_object> [named <calendar name>] [by <distinction>] as <context_var>"
            % (token.split_contents()[0], token.split_contents()[0])
        )
    return CreateCalendarNode(obj, distinction, context_var, name)


# ============================================
# SIMPLE TAGS
# ============================================

@register.simple_tag
def querystring_for_date(date, num=6):
    qs_parts = [
        ("year", date.year),
        ("month", date.month),
        ("day", date.day),
        ("hour", date.hour),
        ("minute", date.minute),
        ("second", date.second),
    ]
    query_string = "?" + urlencode(qs_parts[:num])
    # For compatibility with older Django versions, escape the
    # output. Starting with Django 1.9, simple_tags are automatically
    # passed through conditional_escape(). See:
    # https://docs.djangoproject.com/en/1.9/releases/1.9/#simple-tag-now-wraps-tag-output-in-conditional-escape
    return escape(query_string)


@register.simple_tag
def prev_url(target, calendar, period):
    now = timezone.now()
    delta = now - period.prev().start
    slug = calendar.slug
    if delta.total_seconds() > SCHEDULER_PREVNEXT_LIMIT_SECONDS:
        return ""
    context = {
        "url": "{}{}".format(
            reverse(target, kwargs={"calendar_slug": slug}),
            querystring_for_date(period.prev().start),
        )
    }
    return get_template("schedule/_prev.html").render(context)


@register.simple_tag
def next_url(target, calendar, period):
    now = timezone.now()
    slug = calendar.slug

    delta = period.next().start - now
    if delta.total_seconds() > SCHEDULER_PREVNEXT_LIMIT_SECONDS:
        return ""

    context = {
        "url": "{}{}".format(
            reverse(target, kwargs={"calendar_slug": slug}),
            querystring_for_date(period.next().start),
        )
    }
    return get_template("schedule/_next.html").render(context)


@register.inclusion_tag("schedule/_prevnext.html")
def prevnext(target, calendar, period, fmt=None):
    if fmt is None:
        fmt = settings.DATE_FORMAT
    context = {
        "calendar": calendar,
        "period": period,
        "period_name": format(period.start, fmt),
        "target": target,
    }
    return context


@register.inclusion_tag("schedule/_detail.html")
def detail(occurrence):
    context = {"occurrence": occurrence}
    return context


@register.simple_tag
def hash_occurrence(occ):
    return "{}_{}".format(occ.start.strftime("%Y%m%d%H%M%S"), occ.event.id)


# ============================================
# HELPER FUNCTIONS
# ============================================

def _cook_slots(period, increment):
    """
    Prepare slots to be displayed on the left hand side
    calculate dimensions (in px) for each slot.
    Arguments:
    period - time period for the whole series
    increment - slot size in minutes
    """
    tdiff = datetime.timedelta(minutes=increment)
    num = int((period.end - period.start).total_seconds()) // int(tdiff.total_seconds())
    s = period.start
    slots = []
    for i in range(num):
        sl = period.get_time_slot(s, s + tdiff)
        slots.append(sl)
        s = s + tdiff
    return slots