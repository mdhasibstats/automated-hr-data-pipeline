import glob
import pandas as pd
from pathlib import Path
from data_cleaner import DataCleaner

Path('clean').mkdir(parents=True, exist_ok=True)
Path('reports').mkdir(parents=True, exist_ok=True)

age_map = {
    'eighteen': 18, 'nineteen': 19, 'twenty two': 22, 'twenty five': 25,
    'twenty eight': 28, 'thirty': 30, 'thirty five': 35, 'forty': 40, 'forty five': 45
}

dept_map = {
    'cut': 'Cutting', 'cuttng': 'Cutting',
    'mtn': 'Maintenance', 'maintnance': 'Maintenance',
    'sew': 'Sewing', 'sewing dept': 'Sewing', 'sweing': 'Sewing',
    'finish': 'Finishing', 'finishin': 'Finishing',
    'washng': 'Washing', 'emb': 'Embroidery', 
    'embrodiery': 'Embroidery', 
    'pack': 'Packing', 'pakcing': 'Packing',
    'strore': 'Store', 'stores': 'Store',
    'quality ctrl': 'Quality Control', 'qc': 'Quality Control',
    'administration': 'Admin', 'admn': 'Admin'
}

division_map = {
    'chittagong': 'Chattogram', 'ctg': 'Chattogram',
    'khulana': 'Khulna', 'ghazipur': 'Gazipur',
    'rajshai': 'Rajshahi', 'n.ganj': 'Narayanganj',
    'naraynganj': 'Narayanganj', 'syhlet': 'Sylhet',
    'dkha': 'Dhaka'
}

ranges_map = {
    'age': (18, 60),
    'basic_salary': (0, None),
    'bonus': (0, None),
    'attendance_pct': (0, 100),
    'experience_yrs': (0, 40)
}

config = {
    'dedup_subset': None,
    'id_config': {
        'target_col': 'employee_id',
        'dedup': True
    },
    'phone_col': 'phone',
    'nid_config': {
        'target_column': 'nid',
        'valid_lengths': [10, 13]
    },
    'numeric_mapping_cols': {
        'age': age_map
    },
    'currency_cols': ['basic_salary'],
    'date_cols': ['join_date'],
    'categorical_configs': {
        'department': {'mapping_dict': dept_map, 'title_case': True},
        'division': {'mapping_dict': division_map, 'title_case': True}
    },
    'numeric_bounds': ranges_map,

    'bounds_flag_only': ['age', 'attendance_pct'],
    'name_audit_config': {
        'name_column': 'employee_name',
        'status_column': 'name_status',
        'standardize_verified': True
    },
    'salary_repair_config': {
        'basic_col': 'basic_salary',
        'bonus_col': 'bonus',
        'total_col': 'total_salary'
    },
    'salary_validation_config': {
        'basic_col': 'basic_salary',
        'bonus_col': 'bonus',
        'total_col': 'total_salary',
        'flag_col': 'salary_status',
        'tolerance': 0.01
    },
    'impute_configs': [
        {'columns': ['age'], 'strategy': 'mean', 'groupby_col': 'department', 'int_conversion': True},
        {'columns': ['basic_salary'], 'strategy': 'median', 'groupby_col': 'department'}
    ]
}

# -----------------------------------------------------------------------------------------------------

files = glob.glob('data/*.csv')

if not files:
    print("⚠️ No data files found matching 'data/*.csv'. Please verify your data directory path.")

failed_files = []

for file in files:
    file_path = Path(file)
    print(f"\n⚙️ Processing pipeline initialized for source file: {file_path.name}")


    try:
        df = pd.read_csv(file)
    except Exception as e:
        print(f"❌ Failed to read '{file_path.name}': {e}. Skipping this file.")
        failed_files.append((file_path.name, str(e)))
        continue

    try:
        cleaner = DataCleaner(df)
        cleaner.clean_all(config)

        output_path = Path('clean') / f"{file_path.stem}_clean.xlsx"
        report_path = Path('reports') / f"{file_path.stem}_report.txt"

        cleaner.df.to_excel(output_path, index=False)

        report_text = cleaner.create_reports()
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_text)

        print(report_text)
    except Exception as e:
        print(f"❌ Cleaning pipeline failed on '{file_path.name}': {e}. Skipping this file.")
        failed_files.append((file_path.name, str(e)))
        continue

if failed_files:
    print(f"\n⚠️ {len(failed_files)} file(s) failed during processing:")
    for name, err in failed_files:
        print(f"   - {name}: {err}")
