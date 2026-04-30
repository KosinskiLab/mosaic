{{ objname | escape | underline}}

.. currentmodule:: {{ module }}

.. autoclass:: {{ objname }}
   :members:
   :show-inheritance:

   {% block attributes %}
   {% if attributes %}

   .. rubric:: {{ _('Attributes') }}

   .. autosummary::
      {% for item in attributes %}
         {% if not item.startswith('_') and not item in inherited_members %}
            {{ name }}.{{ item }}
         {% endif %}
      {%- endfor %}
   {% endif %}
   {% endblock %}

   {% block methods %}
   {% if methods %}

   .. rubric:: {{ _('Methods') }}

   .. autosummary::
      {% for item in methods %}
         {% if not item.startswith('_') and not item in inherited_members %}
            {{ name }}.{{ item }}
         {% endif %}
      {%- endfor %}
   {% endif %}
   {% endblock %}