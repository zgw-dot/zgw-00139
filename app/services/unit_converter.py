class UnitConverter:
    VOLUME_UNITS = {
        'l': 1.0,
        'ml': 0.001,
        'ul': 0.000001,
        'nl': 0.000000001,
    }
    
    VOLUME_UNIT_DISPLAY = {
        'l': 'L',
        'ml': 'mL',
        'ul': 'µL',
        'nl': 'nL',
    }
    
    CONCENTRATION_UNITS = {
        'm': 1.0,
        'mm': 0.001,
        'um': 0.000001,
        'nm': 0.000000001,
    }
    
    CONCENTRATION_UNIT_DISPLAY = {
        'm': 'M',
        'mm': 'mM',
        'um': 'µM',
        'nm': 'nM',
    }

    @classmethod
    def _normalize_volume_unit(cls, unit):
        if not unit:
            raise ValueError("单位不能为空")
        unit = unit.strip().lower()
        
        unit = unit.replace('µ', 'u').replace('μ', 'u')
        
        if unit in cls.VOLUME_UNITS:
            return unit
        
        raise ValueError(f"不支持的体积单位: {unit}")

    @classmethod
    def _normalize_conc_unit(cls, unit):
        if not unit:
            raise ValueError("单位不能为空")
        unit = unit.strip().lower()
        
        unit = unit.replace('µ', 'u').replace('μ', 'u')
        
        if unit in cls.CONCENTRATION_UNITS:
            return unit
        
        raise ValueError(f"不支持的浓度单位: {unit}")

    @classmethod
    def convert_volume(cls, value, from_unit, to_unit='ul'):
        from_norm = cls._normalize_volume_unit(from_unit)
        to_norm = cls._normalize_volume_unit(to_unit)
        
        base_value = value * cls.VOLUME_UNITS[from_norm]
        return base_value / cls.VOLUME_UNITS[to_norm]

    @classmethod
    def convert_concentration(cls, value, from_unit, to_unit='uM'):
        from_norm = cls._normalize_conc_unit(from_unit)
        to_norm = cls._normalize_conc_unit(to_unit)
        
        base_value = value * cls.CONCENTRATION_UNITS[from_norm]
        return base_value / cls.CONCENTRATION_UNITS[to_norm]

    @classmethod
    def is_volume_unit(cls, unit):
        try:
            cls._normalize_volume_unit(unit)
            return True
        except ValueError:
            return False

    @classmethod
    def is_concentration_unit(cls, unit):
        try:
            cls._normalize_conc_unit(unit)
            return True
        except ValueError:
            return False

    @classmethod
    def are_units_compatible(cls, unit1, unit2, unit_type='volume'):
        try:
            if unit_type == 'volume':
                cls.convert_volume(1, unit1, unit2)
            else:
                cls.convert_concentration(1, unit1, unit2)
            return True
        except ValueError:
            return False
