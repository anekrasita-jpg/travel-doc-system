class MedicalExpenseForm:
    """
    Manual validation class for the updated Medical Expense form submission.
    """
    def __init__(self, form_data):
        self.staff_id = form_data.get('staff_id', '').strip()
        self.beneficiary_type = form_data.get('beneficiary_type', '').strip()
        self.dependent_id = form_data.get('dependent_id', '').strip()
        self.facility_id = form_data.get('facility_id', '').strip()
        self.treatment_date_start = form_data.get('treatment_date_start', '').strip()
        self.treatment_date_end = form_data.get('treatment_date_end', '').strip()
        self.amount_requested = form_data.get('amount_requested', '').strip()
        self.receipt_count = form_data.get('receipt_count', '').strip()
        # Handle checkbox/toggle boolean state from HTTP POST
        self.is_full_amount = 'is_full_amount' in form_data or form_data.get('is_full_amount') == '1'
        self.amount_approved = form_data.get('amount_approved', '').strip()
        self.errors = {}

    def validate(self):
        # 1. Validate staff_id
        if not self.staff_id:
            self.errors['staff_id'] = 'กรุณาเลือกรายชื่อพนักงานผู้ขอเบิกจ่าย'
        else:
            try:
                int(self.staff_id)
            except ValueError:
                self.errors['staff_id'] = 'รหัสผู้ขอเบิกจ่ายไม่ถูกต้อง'

        # 2. Validate beneficiary_type
        if self.beneficiary_type not in ['self', 'dependent']:
            self.errors['beneficiary_type'] = 'กรุณาระบุว่าต้องการเบิกสิทธิ์ให้ใคร (ตนเอง หรือ บุตร)'

        # 3. Validate dependent_id (required if beneficiary_type is 'dependent')
        if self.beneficiary_type == 'dependent':
            if not self.dependent_id:
                self.errors['dependent_id'] = 'กรุณาเลือกรายชื่อบุตร'
            else:
                try:
                    int(self.dependent_id)
                except ValueError:
                    self.errors['dependent_id'] = 'รหัสบุตรไม่ถูกต้อง'

        # 4. Validate facility_id
        if not self.facility_id:
            self.errors['facility_id'] = 'กรุณาเลือกสถานพยาบาลที่เข้ารับการรักษา'
        else:
            try:
                int(self.facility_id)
            except ValueError:
                self.errors['facility_id'] = 'รหัสสถานพยาบาลไม่ถูกต้อง'

        # 5. Validate dates
        if not self.treatment_date_start:
            self.errors['treatment_date_start'] = 'กรุณาระบุวันที่เริ่มต้นการรักษา'
        if not self.treatment_date_end:
            self.errors['treatment_date_end'] = 'กรุณาระบุวันที่สิ้นสุดการรักษา'

        if self.treatment_date_start and self.treatment_date_end:
            if self.treatment_date_end < self.treatment_date_start:
                self.errors['treatment_date_end'] = 'วันที่สิ้นสุดการรักษาต้องไม่มาก่อนวันที่เริ่มต้นการรักษา'

        # 6. Validate amount_requested
        if not self.amount_requested:
            self.errors['amount_requested'] = 'กรุณากรอกจำนวนเงินที่ต้องการขอเบิก'
        else:
            try:
                req_val = float(self.amount_requested)
                if req_val <= 0:
                    self.errors['amount_requested'] = 'จำนวนเงินที่ขอเบิกต้องมากกว่า 0 บาท'
            except ValueError:
                self.errors['amount_requested'] = 'กรุณากรอกจำนวนเงินเป็นตัวเลขที่ถูกต้อง'

        # 7. Validate receipt_count
        if not self.receipt_count:
            self.errors['receipt_count'] = 'กรุณากรอกจำนวนใบเสร็จรับเงิน'
        else:
            try:
                rc_val = int(self.receipt_count)
                if rc_val <= 0:
                    self.errors['receipt_count'] = 'จำนวนใบเสร็จต้องไม่ต่ำกว่า 1 ใบ'
            except ValueError:
                self.errors['receipt_count'] = 'กรุณากรอกจำนวนใบเสร็จเป็นตัวเลขจำนวนเต็ม'

        # 8. Validate amount_approved (conditional on is_full_amount = False)
        if not self.is_full_amount:
            if not self.amount_approved:
                self.errors['amount_approved'] = 'กรุณากรอกจำนวนเงินที่เบิกได้จริง'
            else:
                try:
                    app_val = float(self.amount_approved)
                    if app_val <= 0:
                        self.errors['amount_approved'] = 'จำนวนเงินที่เบิกได้จริงต้องมากกว่า 0 บาท'
                    elif self.amount_requested:
                        try:
                            req_val = float(self.amount_requested)
                            if app_val > req_val:
                                self.errors['amount_approved'] = 'จำนวนเงินที่เบิกได้จริงต้องไม่เกินจำนวนเงินที่ขอเบิก'
                        except ValueError:
                            pass
                except ValueError:
                    self.errors['amount_approved'] = 'กรุณากรอกจำนวนเงินที่เบิกได้จริงเป็นตัวเลขที่ถูกต้อง'

        return len(self.errors) == 0
