# coding: utf-8
"""
    pyrm - Rechnung
    ~~~~~~~~~~~~~~~~~~~~~~~

    + RechnungsPosten
    + Rechnung

    :copyleft: 2008-2011 by the PyRM team, see AUTHORS for more details.
    :license: GNU GPL v3, see LICENSE.txt for more details.
"""

from django.conf import settings
from django.db import models
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

from creole import creole2html

from pyrm.models.base_models import BaseModel
from decimal import Decimal

#from pyrm.models.base_models import BASE_FIELDSET
#from pyrm.utils.django_modeladmin import add_missing_fields

#______________________________________________________________________________

class RechnungsPostenManager(models.Manager):
    pass


class RechnungsPosten(BaseModel):
    """
    Jede einzelne Position auf einer Rechnung.
    """
    objects = RechnungsPostenManager()

    rechnung = models.ForeignKey(
        "Rechnung", #related_name="positionen"
    )

    beschreibung = models.TextField(
        help_text=u"Rechnungstext für diese Position."
    )
    lieferdatum = models.DateField(null=True, blank=True,
        help_text="Zeitpunkt der Leistungserbringung"
    )
    menge = models.DecimalField(
        max_digits=4, decimal_places=2,
        null=True, blank=True,
        help_text=u"Anzahl der Posten (optional, wenn alle Posten der Rechnung ohne Anzahl ist.)",
    )
    einzelpreis = models.DecimalField(
        max_digits=7, decimal_places=2,
        null=True, blank=True,
        help_text=u"Preis pro Einheit (Netto, einheitlich-optional)"
    )
    einheit = models.CharField(
        max_length=64, null=True, blank=True,
        help_text=u"Einheit z.B. 'std.', 'kg' etc. (optional, nur für Anzeige)"
    )
    mwst = models.DecimalField(
        max_digits=4, decimal_places=2,
        null=True, blank=True,
        default=Decimal(str(settings.PYRM.DEFAULT_MWST)),
        help_text=u"MwSt. für diese Position.",
    )

    order = models.SmallIntegerField(
        null=True, blank=True,
        help_text=u"interne Sortierungsnummer (änderbar, wird automatisch gesetzt, steht nicht auf der Rechnung)"
    )

    def auto_order_posten(self):
        if self.order is not None:
            return

        posten = RechnungsPosten.objects.filter(rechnung=self.rechnung).order_by("-order", "-id").only("id", "order")
        if not posten:
            self.order = 1
        else:
            self.order = posten[0].order + 1

    def save(self, *args, **kwargs):
        self.auto_order_posten()
        super(RechnungsPosten, self).save(*args, **kwargs)

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.menge is None and self.einzelpreis is None:
            self.mwst = None

        if self.menge is None and self.einzelpreis is not None:
            raise ValidationError("'Menge' fehlt.")
        if self.menge is not None and self.einzelpreis is None:
            raise ValidationError("'Einzelpreis' fehlt.")

        if self.menge is not None and self.einzelpreis is not None and self.mwst is None:
            raise ValidationError("'MwSt.' fehlt.")

    def summe(self):
        """ Summe dieses Rechnungsposten Netto """
        if self.menge and self.einzelpreis:
            return self.menge * self.einzelpreis
        else:
            return None

    def beschreibung_html(self):
        html = creole2html(self.beschreibung)
        html = mark_safe(html)
        return html

    def __unicode__(self):
        return self.beschreibung

    class Meta:
        app_label = "pyrm"
        ordering = ("order", "id")
        verbose_name = verbose_name_plural = "Rechnungsposten"




#______________________________________________________________________________

class RechnungManager(models.Manager):
    def create(self, data_dict):
        """
        Create a new entry, use only key-values from the data_dict if a field
        exist.
        """
#        for i in dir(self.model._meta):
#            print i, getattr(self.model._meta, i, "---")

        # Build a list of all existing fieldnames
        field_names = [f.name for f in self.model._meta.fields]

        kwargs = {}
        for key in data_dict:
            if not key in field_names:
                # skip non existing field
                continue
            kwargs[key] = data_dict[key]

        obj = self.model(**kwargs)
        obj.save()
        if not isinstance(obj, models.Model):
            raise AttributeError(obj)
        return obj

    def exist_date_range(self, field_name="datum"):
        """
        Liefert das Datum der ersten und letzten Rechnung zurück.
        """
        def get_date(queryset):
            for item in queryset.iterator():
                if item[0]:
                    return item[0]

        oldest = get_date(
            self.model.objects.values_list(field_name).order_by(field_name)
        )
        newest = get_date(
            self.model.objects.values_list(field_name).order_by("-" + field_name)
        )
        return oldest, newest


class Rechnung(BaseModel):
    """
    Rechnungen die man selber erstellt.
    """
    objects = RechnungManager()

    nummer = models.PositiveIntegerField(
        primary_key=True,
        help_text="Rechnungs Nummer"
    )

    kunde = models.ForeignKey("Kunde", null=True, blank=True)
    anschrift = models.TextField(
        help_text="Abweichende Anschrift",
        null=True, blank=True
    )

    bestellnummer = models.CharField(
        max_length=128, null=True, blank=True,
        help_text="Bestell- bzw. Auftragsnummer"
    )

    datum = models.DateField(null=True, blank=True,
        help_text="Datum der Rechung."
    )
    lieferdatum = models.DateField(null=True, blank=True,
        help_text="Zeitpunkt der Leistungserbringung"
    )
    valuta = models.DateField(null=True, blank=True,
        help_text="Datum der Buchung laut Kontoauszug."
    )

    versand = models.DateField(null=True, blank=True,
        help_text="Versanddatum der Rechnung."
    )

    mahnstufe = models.PositiveIntegerField(default=0,
        help_text="Anzahl der verschickten Mahnungen."
    )

    def posten(self):
        posten = RechnungsPosten.objects.filter(rechnung=self)
        return posten

    def summe(self):
        """ Rechnungs Summe Netto """
        posten = RechnungsPosten.objects.filter(rechnung=self).only("menge", "einzelpreis")
        total_netto = Decimal(0)
        for item in posten:
            summe = item.summe()
            if summe is not None:
                total_netto += item.summe()
        return total_netto

    def get_total(self):
        posten = RechnungsPosten.objects.filter(rechnung=self).only("menge", "einzelpreis", "mwst")
        total_netto = Decimal(0)
        total_brutto = Decimal(0)
        mwst_data = {}
        for item in posten:
            netto = item.summe()
            if netto is None:
                continue
            total_netto += netto

            mwst_proz = item.mwst
            mwst_betrag = netto * mwst_proz / Decimal(100)
            total_brutto += netto + mwst_betrag

            if mwst_proz not in mwst_data:
                mwst_data[mwst_proz] = mwst_betrag
            else:
                mwst_data[mwst_proz] += mwst_betrag

        return total_netto, total_brutto, sorted(mwst_data.items())

    def get_as_html(self):
        context = {
            "instance": self,
            "posten": RechnungsPosten.objects.filter(rechnung=self),
        }
        return render_to_string("pyrm/html_print/rechnung.html", context)

    def __unicode__(self):
        return u"Re.Nr.%s %s %i€" % (self.nummer, self.datum, self.summe())

    class Meta:
        app_label = "pyrm"
        ordering = ['-datum']
        verbose_name = "Rechnung"
        verbose_name_plural = "Rechnungen"



