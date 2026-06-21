import pandas as pd 
import numpy as np
import glob
from pathlib import Path 
import re

class DataCleaner:
    def __init__(self, df):
        self.df = df.copy()
        self.log = []
        self.audit_flags = [] 
        self.before_summary = self._summarize(self.df)
         
    def _summarize(self, df):
        return {
            'rows': df.shape[0], 
            'columns': df.shape[1], 
            'nulls_per_column': df.isnull().sum().to_dict(), 
            'data_types': df.dtypes.to_dict()
        }

    def remove_duplicates(self, subset=None):
        before = len(self.df)
        self.df = self.df.drop_duplicates(subset=subset, ignore_index=True)
        after = len(self.df)
        self.log.append(f"✅ Duplicates handled ==> Removed: {before - after} | Remaining: {after}")
        return self

    def clean_column_names(self):
        self.df.columns = (
            self.df.columns
            .str.strip()
            .str.lower()
            .str.replace(r"[^a-z0-9]+", "_", regex=True)
            .str.strip("_")
        )
        self.log.append("✅ Successfully standardized all column names.")
        return self

    def clean_employee_id_bulletproof(self, target_col='employee_id', dedup=True):
        if target_col not in self.df.columns:
            raise KeyError(f"Column '{target_col}' not found.")
       
        is_not_null = self.df[target_col].notna()
        
        cleaned_series = (self.df.loc[is_not_null, target_col]
                          .astype(str)
                          .str.strip()
                          .str.upper()
                          .str.replace('–', '-', regex=False))
      
        cleaned_series = cleaned_series.str.replace(r'^E-', 'EMP0', regex=True)
        self.df.loc[is_not_null, target_col] = cleaned_series

        if dedup:
            starting_rows = len(self.df)
            self.df = self.df.drop_duplicates(subset=[target_col])
            dropped = starting_rows - len(self.df)
            self.log.append(f"✅ Deduplication ==> Removed {dropped} duplicate rows based on '{target_col}'.")
        
        self.log.append(f"✅ Column '{target_col}' successfully cleaned and anchored.")
        return self

    def clean_phone_bd(self, column):
        original_nulls = self.df[column].isna().sum()
        cleaned_numbers = []

        for val in self.df[column]:
            if pd.isna(val):
                cleaned_numbers.append(np.nan)
                continue
                
            num = str(val).strip().replace('.0', '')
            num = re.sub(r'\D', '', num)
            num = re.sub(r'^(0088|88)', '', num)
            
            if len(num) == 10 and num.startswith('1'):
                num = '0' + num
                
            if len(num) == 11 and num.startswith('01'):
                cleaned_numbers.append(num)
            else:
                cleaned_numbers.append(np.nan)

        self.df[column] = cleaned_numbers
        
        new_nulls = self.df[column].isna().sum()
        self.log.append(f"✅ Phone Cleaner ==> Successfully validated {self.df[column].notna().sum()} numbers. ({new_nulls - original_nulls} unparseable entries flagged as NaN).")
        return self

    def clean_national_id(self, target_column="nid", valid_lengths=(10, 13)):
        if target_column not in self.df.columns:
            raise KeyError(f"Column '{target_column}' not found in DataFrame.")

        national_id = (
            self.df[target_column]
            .astype("string")
            .str.replace(r"\.0$", "", regex=True)
            .str.strip()
        )

        valid_mask = (
            national_id.str.len().isin(valid_lengths)
            & national_id.str.isdigit()
        )

        duplicate_mask = national_id.duplicated(keep=False)
        clean_mask = valid_mask & (~duplicate_mask)
        cleaned_count = (~clean_mask).sum()

        self.df[target_column] = national_id.where(clean_mask, pd.NA)

        self.log.append(f"✅ Replaced {cleaned_count} invalid or duplicate IDs in '{target_column}' with <NA>.")
        return self

    def fix_numeric_columns(self, columns, mapping_dict=None):
        for col in columns:
            if col not in self.df.columns:
                raise KeyError(f"Column '{col}' not found in DataFrame")

            if mapping_dict is not None:
                self.df[col] = self.df[col].replace(mapping_dict)

            self.df[col] = pd.to_numeric(self.df[col], errors="coerce")

        self.log.append(f"✅ Cleaned numeric columns: {columns}")
        return self

    def clean_currency_columns(self, columns):
        for col in columns:
            if col not in self.df.columns:
                raise KeyError(f"Column '{col}' not found in DataFrame.")
            
            cleaned_series = self.df[col].astype(str).str.replace(r'[^0-9.]', '', regex=True)
            self.df[col] = pd.to_numeric(cleaned_series, errors='coerce')
            self.log.append(f"✅ Cleaned currency column: '{col}'")
            
        return self

    def fix_date_columns(self, columns):
        for col in columns:
            if col not in self.df.columns:
                raise KeyError(f"Column '{col}' not found in DataFrame.")
                
            self.df[col] = pd.to_datetime(self.df[col], format='mixed', errors='coerce')
            
        self.log.append(f"✅ Cleaned date columns: {columns}")
        return self

    def enforce_flexible_bounds(self, bounds_config):
        for col, bounds in bounds_config.items():
            if col not in self.df.columns:
                raise KeyError(f"Column '{col}' not found in DataFrame.")
                
            min_val, max_val = bounds
            out_of_bounds_mask = pd.Series(False, index=self.df.index)
            
            if min_val is not None:
                out_of_bounds_mask |= (self.df[col] < min_val)
                
            if max_val is not None:
                out_of_bounds_mask |= (self.df[col] > max_val)
                
            flagged_count = out_of_bounds_mask.sum()
            
            if flagged_count > 0:
                self.df.loc[out_of_bounds_mask, col] = np.nan
                range_desc = f"Min: {min_val if min_val is not None else 'None'} | Max: {max_val if max_val is not None else 'None'}"
                self.log.append(f"✅ Coerced {flagged_count:4d} rows to NaN in '{col}' ({range_desc})")
            else:
                self.log.append(f"✅ Verified '{col}': All values within specified limits.")
                
        return self

    def impute_basic_salary_from_total(self, basic_col, bonus_col, total_col):
        for col in [basic_col, bonus_col, total_col]:
            if col not in self.df.columns:
                raise KeyError(f"Column '{col}' is missing from the DataFrame.")
                
        repair_mask = ((self.df[basic_col] == 0) | (self.df[basic_col].isna())) & (self.df[total_col] > self.df[bonus_col])
        rows_to_repair = repair_mask.sum()
        
        if rows_to_repair > 0:
            calculated_basic = self.df.loc[repair_mask, total_col] - self.df.loc[repair_mask, bonus_col]
            self.df.loc[repair_mask, basic_col] = calculated_basic
            self.log.append(f"✅ Successfully repaired {rows_to_repair} rows where basic salary was missing/0 using {basic_col} = {total_col} - {bonus_col}")
        else:
            self.log.append("No rows matched the criteria for deductive basic salary imputation.")
            
        return self

    def clean_categorical_column(self, target_column, mapping_dict=None, title_case=True):
        if target_column not in self.df.columns:
            self.log.append(f"⚠️ Warning: '{target_column}' not found in DataFrame. Skipping.")
            return self

        self.df[target_column] = (
            self.df[target_column]
            .astype("string")
            .str.strip()
            .str.lower()
        )

        if mapping_dict is not None:
            self.df[target_column] = self.df[target_column].replace(mapping_dict)
        if title_case:
            self.df[target_column] = self.df[target_column].str.title()

        self.log.append(f"✅ Successfully cleaned column: '{target_column}'")
        return self

    def audit_employee_names(self, name_column="employee_name", status_column="name_status"):
        if name_column not in self.df.columns:
            raise KeyError(f"Column '{name_column}' not found in DataFrame.")

        bengali_pattern = r"[\u0980-\u09FF]"
        english_pattern = r"[A-Za-z]"

        has_bengali = (
            self.df[name_column]
            .astype("string")
            .str.contains(bengali_pattern, regex=True, na=False)
        )

        has_english = (
            self.df[name_column]
            .astype("string")
            .str.contains(english_pattern, regex=True, na=False)
        )

        mixed_script = has_bengali & has_english

        self.df[status_column] = "Verified"
        self.df.loc[mixed_script, status_column] = "Mixed Script Discrepancy"

        anomaly_count = mixed_script.sum()
        self.audit_flags.append(status_column)

        self.log.append(f"✅ Name Audit Complete: Found {anomaly_count} mixed-script discrepancies.")
        return self

    def standardize_verified_names(self, name_column="employee_name", status_column="name_status", verified_label="Verified"):
        mask = self.df[status_column] == verified_label

        self.df.loc[mask, name_column] = (
            self.df.loc[mask, name_column]
            .astype("string")
            .str.strip()
            .str.lower()
            .str.title()
        )

        self.log.append(f"✅ Standardized {mask.sum()} verified employee names.")
        return self

    def impute_statistical_missing(self, columns, strategy="median", groupby_col=None, int_conversion=False):
        if strategy not in {"median", "mean"}:
            raise ValueError("strategy must be either 'median' or 'mean'.")

        for col in columns:
            if col not in self.df.columns:
                self.log.append(f"⚠️ Warning: '{col}' not found in DataFrame. Skipping.")
                continue

            if not pd.api.types.is_numeric_dtype(self.df[col]):
                self.log.append(f"⚠️ Warning: '{col}' is not numeric. Skipping.")
                continue

            missing_mask = self.df[col].isna()
            missing_count = missing_mask.sum()

            if missing_count == 0:
                self.log.append(f"✅ '{col}' contains no missing values.")
                continue

            audit_col = f"{col}_imputed"
            self.df[audit_col] = missing_mask
            self.audit_flags.append(audit_col)

            if groupby_col and groupby_col in self.df.columns:
                if strategy == "median":
                    fill_values = (
                        self.df.groupby(groupby_col)[col]
                        .transform("median")
                    )
                else:
                    fill_values = (
                        self.df.groupby(groupby_col)[col]
                        .transform("mean")
                    )
                self.df[col] = self.df[col].fillna(fill_values)

            else:
                if strategy == "median":
                    fill_value = self.df[col].median()
                else:
                    fill_value = self.df[col].mean()
                self.df[col] = self.df[col].fillna(fill_value)

            self.log.append(f"✅ Filled {missing_count:4d} missing values in '{col}' using {strategy}. Audit flag: '{audit_col}'")
            
            if int_conversion:
               if not self.df[col].isna().any():
                  self.df[col] = self.df[col].round().astype(int)

        return self

    def validate_salary_totals(self, basic_col, bonus_col, total_col, flag_col='salary_status', tolerance=0.01):
        for col in [basic_col, bonus_col, total_col]:
            if col not in self.df.columns:
                raise KeyError(f"Required column '{col}' missing from the DataFrame.")
                
        expected_total = self.df[basic_col].fillna(0) + self.df[bonus_col].fillna(0)
        actual_total = self.df[total_col].fillna(0)
        
        abs_diff = (expected_total - actual_total).abs()
        
        self.df[flag_col] = np.where(abs_diff <= tolerance, 'Verified', 'Discrepancy')
        self.audit_flags.append(flag_col)
        
        discrepancy_count = (self.df[flag_col] == 'Discrepancy').sum()
        self.log.append(f"✅ Validation Column '{flag_col}' created successfully. {discrepancy_count} discrepancies flagged.")
        
        return self

    def clean_all(self, config):
     
        self.remove_duplicates(subset=config.get('dedup_subset'))
        self.clean_column_names()
        
        if config.get('id_config'):
            self.clean_employee_id_bulletproof(**config.get('id_config'))
            
        if config.get('phone_col'):
            self.clean_phone_bd(column=config.get('phone_col'))
            
        if config.get('nid_config'):
            self.clean_national_id(**config.get('nid_config'))
            
        if config.get('numeric_mapping_cols'):
            for col, mapping in config.get('numeric_mapping_cols').items():
                self.fix_numeric_columns(columns=[col], mapping_dict=mapping)
                
        if config.get('currency_cols'):
            self.clean_currency_columns(config.get('currency_cols'))
            
        if config.get('date_cols'):
            self.fix_date_columns(config.get('date_cols'))
            
        if config.get('numeric_bounds'):
            self.enforce_flexible_bounds(bounds_config=config.get('numeric_bounds'))
            
        if config.get('categorical_configs'):
            for col, kwargs in config.get('categorical_configs').items():
                self.clean_categorical_column(target_column=col, **kwargs)
                
        if config.get('name_audit_config'):
            audit_kwargs = config.get('name_audit_config')
            self.audit_employee_names(
                name_column=audit_kwargs.get('name_column', 'employee_name'), 
                status_column=audit_kwargs.get('status_column', 'name_status')
            )
            if audit_kwargs.get('standardize_verified'):
                self.standardize_verified_names(
                    name_column=audit_kwargs.get('name_column', 'employee_name'),
                    status_column=audit_kwargs.get('status_column', 'name_status')
                )
                
        if config.get('impute_configs'):
            for imp_config in config.get('impute_configs'):
                self.impute_statistical_missing(**imp_config)
                
        if config.get('salary_validation_config'):
            self.validate_salary_totals(**config.get('salary_validation_config'))
                
        return self

    def create_reports(self):
        after_summary = self._summarize(self.df)
        
        report_lines = []
        report_lines.append('='*100)
        report_lines.append('DATA QUALITY REPORT')
        report_lines.append('='*100)

        report_lines.append("\n-------------Data Shape: Before ==> After-----------------")
        report_lines.append(f"Rows: {self.before_summary['rows']} => {after_summary['rows']}")
        report_lines.append(f"Columns: {self.before_summary['columns']} => {after_summary['columns']}")
        
        report_lines.append("\n--------------Null values: before => after-----------------")
        old_cols = list(self.before_summary['nulls_per_column'].keys())
        new_cols = list(after_summary['nulls_per_column'].keys())
        for old_col, new_col in zip(old_cols, new_cols):
            before_nulls = self.before_summary['nulls_per_column'][old_col]
            after_nulls = after_summary['nulls_per_column'][new_col]
            if before_nulls > 0 or after_nulls > 0: 
                report_lines.append(f"{new_col}: {before_nulls} ==> {after_nulls}")

        report_lines.append("\n-------------Cleaning Steps Applied-----------------")
        for entry in self.log:
            report_lines.append(f" - {entry}")
            
        if self.audit_flags:
            report_lines.append("\n-------------Audit Columns Added-----------------")
            for flag in self.audit_flags:
                report_lines.append(f" Flag: {flag}")
        
        report_lines.append("\n-------------Data Types After Cleaning-----------------")
        for col, dtype in after_summary['data_types'].items():
            report_lines.append(f"{col} : {dtype}")
            
        return "\n".join(report_lines)