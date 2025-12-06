from django.contrib import admin

from schedule.forms import EventAdminForm
from schedule.models import (
    Calendar,
    CalendarRelation,
    Event,
    EventRelation,
    Occurrence,
    Rule,
)


@admin.register(Calendar)
class CalendarAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "empresa")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ["name", "empresa__razon_social", "empresa__emisor_rfc"]
    list_filter = ("empresa",)  # Filtro por empresa
    fieldsets = (
        (None, {
            "fields": [
                "empresa",  # Campo empresa
                ("name", "slug")
            ]
        }),
    )
    
    def get_queryset(self, request):
        """
        Filtrar calendarios por empresa si el usuario no es superusuario
        """
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        
        # Si el usuario tiene perfil con empresa asignada
        if hasattr(request.user, 'profile') and request.user.profile.empresa:
            return qs.filter(empresa=request.user.profile.empresa)
        
        return qs.none()
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """
        Limitar las opciones de empresa según el usuario
        """
        if db_field.name == "empresa":
            if not request.user.is_superuser:
                # Usuarios no superusuarios solo ven su empresa
                if hasattr(request.user, 'profile') and request.user.profile.empresa:
                    kwargs["queryset"] = request.user.profile.empresa.__class__.objects.filter(
                        id=request.user.profile.empresa.id
                    )
            # Superusuarios ven todas las empresas (no se limita el queryset)
        
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(CalendarRelation)
class CalendarRelationAdmin(admin.ModelAdmin):
    list_display = ("calendar", "content_object", "get_empresa")
    list_filter = ("inheritable", "calendar__empresa")
    search_fields = ["calendar__name", "calendar__empresa__razon_social"]
    fieldsets = (
        (
            None,
            {
                "fields": [
                    "calendar",
                    ("content_type", "object_id", "distinction"),
                    "inheritable",
                ]
            },
        ),
    )
    
    def get_empresa(self, obj):
        """Mostrar empresa del calendario"""
        return obj.calendar.empresa.razon_social if obj.calendar.empresa else "-"
    get_empresa.short_description = "Empresa"
    get_empresa.admin_order_field = "calendar__empresa"
    
    def get_queryset(self, request):
        """Filtrar por empresa del usuario"""
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        
        if hasattr(request.user, 'profile') and request.user.profile.empresa:
            return qs.filter(calendar__empresa=request.user.profile.empresa)
        
        return qs.none()


@admin.register(EventRelation)
class EventRelationAdmin(admin.ModelAdmin):
    list_display = ("event", "content_object", "distinction", "get_empresa")
    list_filter = ("event__calendar__empresa",)
    search_fields = ["event__title", "event__calendar__empresa__razon_social"]
    fieldsets = (
        (None, {"fields": ["event", ("content_type", "object_id", "distinction")]}),
    )
    
    def get_empresa(self, obj):
        """Mostrar empresa del evento"""
        return obj.event.calendar.empresa.razon_social if obj.event.calendar.empresa else "-"
    get_empresa.short_description = "Empresa"
    get_empresa.admin_order_field = "event__calendar__empresa"
    
    def get_queryset(self, request):
        """Filtrar por empresa del usuario"""
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        
        if hasattr(request.user, 'profile') and request.user.profile.empresa:
            return qs.filter(event__calendar__empresa=request.user.profile.empresa)
        
        return qs.none()

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "start", "end", "calendar", "get_empresa")
    list_filter = ("start", "calendar__empresa")
    ordering = ("-start",)
    date_hierarchy = "start"
    search_fields = ("title", "description", "calendar__name", "calendar__empresa__razon_social")
    autocomplete_fields = ['calendar']  # Mejor para muchos calendarios
    fieldsets = (
        (
            None,
            {
                "fields": [
                    ("title", "color_event"),
                    ("description",),
                    ("start", "end"),
                    ("creator", "calendar"),
                    ("rule", "end_recurring_period"),
                ]
            },
        ),
    )
    form = EventAdminForm
    
    def get_empresa(self, obj):
        """Mostrar empresa del calendario"""
        return obj.calendar.empresa.razon_social if obj.calendar.empresa else "-"
    get_empresa.short_description = "Empresa"
    get_empresa.admin_order_field = "calendar__empresa"
    
    def get_queryset(self, request):
        """Filtrar por empresa del usuario"""
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        
        if hasattr(request.user, 'profile') and request.user.profile.empresa:
            return qs.filter(calendar__empresa=request.user.profile.empresa)
        
        return qs.none()
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """
        Limitar las opciones de calendario según la empresa del usuario
        """
        if db_field.name == "calendar":
            if not request.user.is_superuser:
                if hasattr(request.user, 'profile') and request.user.profile.empresa:
                    kwargs["queryset"] = Calendar.objects.filter(
                        empresa=request.user.profile.empresa
                    )
        
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Occurrence)
class OccurrenceAdmin(admin.ModelAdmin):
    list_display = ("title", "start", "end", "event", "cancelled", "get_empresa")
    list_filter = ("cancelled", "start", "event__calendar__empresa")
    search_fields = ("title", "description", "event__title", "event__calendar__empresa__razon_social")
    date_hierarchy = "start"
    ordering = ("-start",)
    
    fieldsets = (
        (
            None,
            {
                "fields": [
                    "event",
                    ("title", "description"),
                    ("start", "end"),
                    ("original_start", "original_end"),
                    "cancelled",
                ]
            },
        ),
    )
    
    def get_empresa(self, obj):
        """Mostrar empresa del evento"""
        return obj.event.calendar.empresa.razon_social if obj.event.calendar.empresa else "-"
    get_empresa.short_description = "Empresa"
    get_empresa.admin_order_field = "event__calendar__empresa"
    
    def get_queryset(self, request):
        """Filtrar por empresa del usuario"""
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        
        if hasattr(request.user, 'profile') and request.user.profile.empresa:
            return qs.filter(event__calendar__empresa=request.user.profile.empresa)
        
        return qs.none()


@admin.register(Rule)
class RuleAdmin(admin.ModelAdmin):
    list_display = ("name", "frequency")
    list_filter = ("frequency",)
    search_fields = ("name", "description")