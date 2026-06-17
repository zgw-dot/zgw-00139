import json
from app.services.unit_converter import UnitConverter

class LiquidHandlingEngine:
    
    DEFAULT_MASTER_MIX_VOLUME_RATIO = 0.5
    DEFAULT_PRIMER_VOLUME_RATIO = 0.1
    DEFAULT_SAMPLE_VOLUME_RATIO = 0.1
    DEFAULT_MIN_PIPETTE_VOLUME = 0.5
    DEFAULT_MIN_PIPETTE_UNIT = 'ul'
    
    def calculate_well_recipe(self, sample, primer, master_mix_reagent, water_reagent, 
                              total_volume, total_volume_unit='ul', min_pipette_volume=None):
        if min_pipette_volume is None:
            min_pipette_volume = self.DEFAULT_MIN_PIPETTE_VOLUME
            min_pipette_unit = self.DEFAULT_MIN_PIPETTE_UNIT
        else:
            min_pipette_unit = 'ul'
        
        total_vol_ul = UnitConverter.convert_volume(total_volume, total_volume_unit, 'ul')
        
        sample_vol_ul = total_vol_ul * self.DEFAULT_SAMPLE_VOLUME_RATIO
        primer_vol_ul = total_vol_ul * self.DEFAULT_PRIMER_VOLUME_RATIO
        master_mix_vol_ul = total_vol_ul * self.DEFAULT_MASTER_MIX_VOLUME_RATIO
        water_vol_ul = total_vol_ul - sample_vol_ul - primer_vol_ul - master_mix_vol_ul
        
        warnings = []
        
        if sample_vol_ul < min_pipette_volume:
            warnings.append({
                'type': 'min_pipette',
                'component': 'sample',
                'volume': sample_vol_ul,
                'unit': 'ul',
                'min_volume': min_pipette_volume,
                'min_unit': min_pipette_unit,
                'message': f'样本体积 {sample_vol_ul:.2f} µL 低于最小移液体积 {min_pipette_volume} µL'
            })
        
        if primer_vol_ul < min_pipette_volume:
            warnings.append({
                'type': 'min_pipette',
                'component': 'primer',
                'volume': primer_vol_ul,
                'unit': 'ul',
                'min_volume': min_pipette_volume,
                'min_unit': min_pipette_unit,
                'message': f'引物体积 {primer_vol_ul:.2f} µL 低于最小移液体积 {min_pipette_volume} µL'
            })
        
        if master_mix_vol_ul < min_pipette_volume:
            warnings.append({
                'type': 'min_pipette',
                'component': 'master_mix',
                'volume': master_mix_vol_ul,
                'unit': 'ul',
                'min_volume': min_pipette_volume,
                'min_unit': min_pipette_unit,
                'message': f'Master Mix 体积 {master_mix_vol_ul:.2f} µL 低于最小移液体积 {min_pipette_volume} µL'
            })
        
        return {
            'sample_volume': sample_vol_ul,
            'sample_volume_unit': 'ul',
            'primer_volume': primer_vol_ul,
            'primer_volume_unit': 'ul',
            'master_mix_volume': master_mix_vol_ul,
            'master_mix_unit': 'ul',
            'water_volume': water_vol_ul,
            'water_unit': 'ul',
            'total_volume': total_vol_ul,
            'total_volume_unit': 'ul',
            'warnings': warnings
        }
    
    def calculate_control_well(self, control_type, primer, master_mix_reagent, water_reagent,
                               total_volume, total_volume_unit='ul', min_pipette_volume=None):
        if min_pipette_volume is None:
            min_pipette_volume = self.DEFAULT_MIN_PIPETTE_VOLUME
        
        total_vol_ul = UnitConverter.convert_volume(total_volume, total_volume_unit, 'ul')
        
        primer_vol_ul = total_vol_ul * self.DEFAULT_PRIMER_VOLUME_RATIO
        master_mix_vol_ul = total_vol_ul * self.DEFAULT_MASTER_MIX_VOLUME_RATIO
        sample_vol_ul = 0
        water_vol_ul = total_vol_ul - primer_vol_ul - master_mix_vol_ul
        
        if control_type == 'positive':
            sample_vol_ul = total_vol_ul * self.DEFAULT_SAMPLE_VOLUME_RATIO
            water_vol_ul = total_vol_ul - sample_vol_ul - primer_vol_ul - master_mix_vol_ul
        
        warnings = []
        if primer_vol_ul < min_pipette_volume:
            warnings.append({
                'type': 'min_pipette',
                'component': 'primer',
                'volume': primer_vol_ul,
                'unit': 'ul',
                'min_volume': min_pipette_volume,
                'min_unit': 'ul',
                'message': f'引物体积 {primer_vol_ul:.2f} µL 低于最小移液体积 {min_pipette_volume} µL'
            })
        if master_mix_vol_ul < min_pipette_volume:
            warnings.append({
                'type': 'min_pipette',
                'component': 'master_mix',
                'volume': master_mix_vol_ul,
                'unit': 'ul',
                'min_volume': min_pipette_volume,
                'min_unit': 'ul',
                'message': f'Master Mix 体积 {master_mix_vol_ul:.2f} µL 低于最小移液体积 {min_pipette_volume} µL'
            })
        
        return {
            'sample_volume': sample_vol_ul,
            'sample_volume_unit': 'ul',
            'primer_volume': primer_vol_ul,
            'primer_volume_unit': 'ul',
            'master_mix_volume': master_mix_vol_ul,
            'master_mix_unit': 'ul',
            'water_volume': water_vol_ul,
            'water_unit': 'ul',
            'total_volume': total_vol_ul,
            'total_volume_unit': 'ul',
            'warnings': warnings
        }
    
    def check_inventory_sufficient(self, reagent, required_volume, required_unit='ul'):
        available_vol = UnitConverter.convert_volume(reagent['volume'], reagent['volume_unit'], 'ul')
        required_vol = UnitConverter.convert_volume(required_volume, required_unit, 'ul')
        return available_vol >= required_vol, available_vol, required_vol
    
    def check_well_conflicts(self, template_wells):
        well_map = {}
        conflicts = []
        
        for well in template_wells:
            key = (well['well_row'], well['well_col'])
            if key in well_map:
                conflicts.append({
                    'well': f"{chr(64 + well['well_row'])}{well['well_col']}",
                    'existing': well_map[key],
                    'new': well
                })
            well_map[key] = well
        
        return conflicts
