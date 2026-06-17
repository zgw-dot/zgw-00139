import csv
import json
import io

class DataImporter:
    
    @staticmethod
    def parse_samples_csv(csv_content):
        samples = []
        reader = csv.DictReader(io.StringIO(csv_content))
        
        for row in reader:
            sample = {
                'name': row.get('name', '').strip(),
                'concentration': float(row.get('concentration', 0)),
                'concentration_unit': row.get('concentration_unit', 'uM').strip(),
                'volume': float(row.get('volume', 0)),
                'volume_unit': row.get('volume_unit', 'ul').strip(),
                'description': row.get('description', '').strip(),
            }
            if sample['name']:
                samples.append(sample)
        
        return samples
    
    @staticmethod
    def parse_primers_csv(csv_content):
        primers = []
        reader = csv.DictReader(io.StringIO(csv_content))
        
        for row in reader:
            primer = {
                'name': row.get('name', '').strip(),
                'sequence': row.get('sequence', '').strip(),
                'concentration': float(row.get('concentration', 0)),
                'concentration_unit': row.get('concentration_unit', 'uM').strip(),
                'volume': float(row.get('volume', 0)),
                'volume_unit': row.get('volume_unit', 'ul').strip(),
                'melting_temp': float(row.get('melting_temp', 0)) if row.get('melting_temp') else None,
                'description': row.get('description', '').strip(),
            }
            if primer['name']:
                primers.append(primer)
        
        return primers
    
    @staticmethod
    def parse_reagents_csv(csv_content):
        reagents = []
        reader = csv.DictReader(io.StringIO(csv_content))
        
        for row in reader:
            reagent = {
                'name': row.get('name', '').strip(),
                'type': row.get('type', '').strip(),
                'concentration': float(row.get('concentration', 0)) if row.get('concentration') else None,
                'concentration_unit': row.get('concentration_unit', '').strip(),
                'volume': float(row.get('volume', 0)),
                'volume_unit': row.get('volume_unit', 'ul').strip(),
                'min_pipette_volume': float(row.get('min_pipette_volume', 0)) if row.get('min_pipette_volume') else None,
                'min_pipette_unit': row.get('min_pipette_unit', 'ul').strip() if row.get('min_pipette_unit') else 'ul',
                'description': row.get('description', '').strip(),
            }
            if reagent['name']:
                reagents.append(reagent)
        
        return reagents
    
    @staticmethod
    def parse_template_csv(csv_content):
        rows = []
        reader = csv.reader(io.StringIO(csv_content))
        
        for row in reader:
            rows.append(row)
        
        if not rows:
            return None
        
        return DataImporter._parse_template_grid(rows)
    
    @staticmethod
    def _parse_template_grid(grid_rows):
        num_rows = len(grid_rows) - 1
        num_cols = len(grid_rows[0]) - 1
        
        wells = []
        
        for r_idx, row in enumerate(grid_rows[1:], start=1):
            for c_idx, cell in enumerate(row[1:], start=1):
                cell = cell.strip() if cell else ''
                
                well_type = 'sample'
                sample_name = None
                note = None
                
                if cell == 'PC' or cell.lower() == 'positive':
                    well_type = 'positive_control'
                elif cell == 'NC' or cell.lower() == 'negative':
                    well_type = 'negative_control'
                elif cell == 'EMPTY' or cell == '' or cell.lower() == 'empty':
                    well_type = 'empty'
                elif cell.startswith('S') or cell.startswith('Sample'):
                    well_type = 'sample'
                    sample_name = cell
                else:
                    well_type = 'sample'
                    sample_name = cell
                
                wells.append({
                    'well_row': r_idx,
                    'well_col': c_idx,
                    'well_type': well_type,
                    'sample_name': sample_name,
                    'note': note,
                })
        
        return {
            'rows': num_rows,
            'cols': num_cols,
            'wells': wells,
        }
    
    @staticmethod
    def parse_json(json_content):
        return json.loads(json_content)
