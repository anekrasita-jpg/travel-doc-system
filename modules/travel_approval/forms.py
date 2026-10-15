class TravelApprovalForm:
    """
    Manual validation class for Travel Approval form submission.
    """
    def __init__(self, form_data):
        self.staff_id = form_data.get('staff_id', '').strip()
        self.document_number = form_data.get('document_number', '').strip()
        self.date_start = form_data.get('date_start', '').strip()
        self.date_end = form_data.get('date_end', '').strip()
        self.purpose = form_data.get('purpose', '').strip()
        self.vehicle_id = form_data.get('vehicle_id', '').strip()
        self.acting_replacement = form_data.get('acting_replacement', '').strip()
        self.acting_replacement_position = form_data.get('acting_replacement_position', '').strip()
        
        # Parse companion IDs from form data
        if hasattr(form_data, 'getlist'):
            raw_companions = form_data.getlist('companion_staff_id[]')
        else:
            raw_companions = form_data.get('companion_staff_id[]', [])
            if isinstance(raw_companions, str):
                raw_companions = [raw_companions]
        
        self.companion_staff_ids = []
        for cid in raw_companions:
            if str(cid).strip():
                try:
                    self.companion_staff_ids.append(int(cid))
                except ValueError:
                    pass
                    
        self.errors = {}

    def validate(self):
        if not self.staff_id:
            self.errors['staff_id'] = 'กรุณาเลือกชื่อพนักงานผู้ขออนุมัติ'
        else:
            try:
                int(self.staff_id)
            except ValueError:
                self.errors['staff_id'] = 'รหัสพนักงานไม่ถูกต้อง'

        if not self.date_start:
            self.errors['date_start'] = 'กรุณาระบุวันที่เริ่มเดินทาง'

        if not self.date_end:
            self.errors['date_end'] = 'กรุณาระบุวันที่สิ้นสุดการเดินทาง'

        if self.date_start and self.date_end:
            if self.date_start > self.date_end:
                self.errors['date_end'] = 'วันที่สิ้นสุดต้องไม่ก่อนวันที่เริ่มเดินทาง'

        if not self.purpose:
            self.errors['purpose'] = 'กรุณากรอกเหตุผลหรือวัตถุประสงค์ในการปฏิบัติงาน'

        if not self.vehicle_id:
            self.errors['vehicle_id'] = 'กรุณาเลือกยานพาหนะ'
        else:
            try:
                int(self.vehicle_id)
            except ValueError:
                self.errors['vehicle_id'] = 'รหัสยานพาหนะไม่ถูกต้อง'

        if len(self.companion_staff_ids) > 4:
            self.errors['companion_staff_id'] = 'เลือกผู้ร่วมเดินทางได้ไม่เกิน 4 คน'

        return len(self.errors) == 0
