def generate_component_name(instance_name=None, hostgroup_name=None, tags=None) -> str:
    """
    Derive a component name from an instance name using the following rules:

    Hyphen-based rules (evaluated first):
      >2 hyphens  : everything before the 3rd hyphen  (a-b-c-d  -> a-b-c)
      2 hyphens   : everything before the 2nd hyphen  (a-b-c    -> a-b)
      1 hyphen    : no component (return None)
          EXCEPT when there is also 1+ period AND the hyphen comes before
          the first period -> everything before the first period  (a-b.c.d -> a-b)

    No-hyphen rules:
      0 periods   : no component (return None)
      1+ periods  : strip '.fedex.com' suffix if present, then:
                      0 or 1 period remaining -> use the whole string
                      2+ periods remaining    -> everything before the 2nd period
    """
    if not instance_name:
        return None

    name = instance_name
    hyphen_count = name.count('-')

    # ── Hyphen-based rules ────────────────────────────────────────────────────

    if hyphen_count > 2:
        # everything before the 3rd hyphen
        parts = name.split('-')
        return '-'.join(parts[:3])

    if hyphen_count == 2:
        # everything before the 2nd hyphen
        parts = name.split('-')
        return '-'.join(parts[:2])

    if hyphen_count == 1:
        period_count = name.count('.')
        if period_count >= 1:
            hyphen_pos = name.index('-')
            period_pos = name.index('.')
            if hyphen_pos < period_pos:
                # hyphen is first: everything before the first period
                return name[:period_pos]
        # 1 hyphen with no periods, or period comes before hyphen
        return None

    # ── No-hyphen rules ───────────────────────────────────────────────────────

    if name.count('.') == 0:
        return None

    # Strip .fedex.com if present
    if name.endswith('.fedex.com'):
        name = name[: -len('.fedex.com')]

    period_count = name.count('.')
    if period_count <= 1:
        return name

    # 2+ periods remaining: everything before the 2nd period
    parts = name.split('.')
    return '.'.join(parts[:2])
