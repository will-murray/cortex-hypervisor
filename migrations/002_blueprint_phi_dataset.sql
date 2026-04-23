-- Migration 002: Blueprint_PHI dataset + tables (regenerated from updated schemas)
-- Run with: bq query --use_legacy_sql=false < 002_blueprint_phi_dataset.sql
--   (substitute {GCP_PROJECT} first)

-- Create dataset first (via bq mk):
--   bq mk --dataset --location=US {GCP_PROJECT}:Blueprint_PHI

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.Accessories` (
  branch_id STRING,
  accessory_id STRING,
  accessory_desc STRING,
  category STRING,
  catalog_no STRING,
  vendor_price STRING,
  client_price STRING,
  returnable STRING,
  active STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.AlternativeContact` (
  branch_id STRING,
  client_id STRING,
  salutation STRING,
  relation STRING,
  given_name STRING,
  surname STRING,
  initial STRING,
  email_address STRING,
  home_telephone_no STRING,
  work_telephone_no STRING,
  work_extension STRING,
  mobile_telephone_no STRING,
  unit STRING,
  street_no STRING,
  street_name STRING,
  city STRING,
  province_name STRING,
  country_name STRING,
  postal_code STRING,
  bill_to_contact STRING,
  primary_contact STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.Appointments` (
  branch_id STRING,
  event_id STRING,
  event_type STRING,
  start_time STRING,
  end_time STRING,
  client_id STRING,
  title STRING,
  notes STRING,
  status STRING,
  status_2 STRING,
  practitioner STRING,
  location_name STRING,
  arrived_time STRING,
  completed_time STRING,
  created_time STRING,
  sales_opportunity STRING,
  referrer_type_id STRING,
  referral_source_id STRING,
  creator_id STRING,
  arrived_time_2 STRING,
  in_progress_time STRING,
  completed_time_2 STRING,
  journal_note_required STRING,
  unaidable STRING,
  third_party_present STRING,
  online_booking STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.AudioImpedance` (
  branch_id STRING,
  entry_id STRING,
  side STRING,
  signal_level STRING,
  signal_type STRING,
  signal_output STRING,
  frequency STRING,
  pressure STRING,
  probe_frequency STRING,
  test_type STRING,
  volume STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.AudioTonePoint` (
  branch_id STRING,
  entry_id STRING,
  side STRING,
  stimulus_frequency STRING,
  stimulus_level STRING,
  tone_point_type STRING,
  tone_point_status STRING,
  masking_level STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.Audiograms` (
  branch_id STRING,
  client_id STRING,
  entry_id STRING,
  entry_date STRING,
  user STRING,
  hearing_loss_severity_left STRING,
  left_ear_loss_severity STRING,
  hearing_loss_severity_right STRING,
  right_ear_loss_severity STRING,
  left_ear_loss_type STRING,
  right_ear_loss_type STRING,
  left_ear_loss_shape STRING,
  right_ear_loss_shape STRING,
  test_method STRING,
  noah_action_date STRING,
  srt_right STRING,
  srt_mask_right STRING,
  srt_left STRING,
  srt_mask_left STRING,
  srt_binaural STRING,
  wr_percent_right STRING,
  wr_right STRING,
  wr_mask_right STRING,
  wr_percent_left STRING,
  wr_left STRING,
  wr_mask_left STRING,
  wr_percent_binaural STRING,
  wr_binaural STRING,
  wrn_percent_right STRING,
  wrn_right STRING,
  wrn_noise_right STRING,
  wrn_percent_left STRING,
  wrn_left STRING,
  wrn_noise_left STRING,
  wrn_percent_binaural STRING,
  wrn_binaural STRING,
  wrn_noise_binaural STRING,
  speech_mcl_right STRING,
  speech_mcl_left STRING,
  speech_mcl_binaural STRING,
  speech_ucl_right STRING,
  speech_ucl_left STRING,
  speech_ucl_binaural STRING,
  audiometer_last_calibration_date STRING,
  tympanogram_test_type_right STRING,
  tympanogram_test_pressure_right STRING,
  tympanogram_test_compliance_right STRING,
  tympanogram_test_volume_right STRING,
  tympanogram_test_width_right STRING,
  tympanogram_test_probe_frequency_right STRING,
  tympanogram_test_type_left STRING,
  tympanogram_test_pressure_left STRING,
  tympanogram_test_compliance_left STRING,
  tympanogram_test_volume_left STRING,
  tympanogram_test_width_left STRING,
  tympanogram_test_probe_frequency_left STRING,
  audiometer_id STRING,
  tympanogram_test_compliance_right_unit STRING,
  tympanogram_test_volume_right_unit STRING,
  tympanogram_test_width_right_unit STRING,
  tympanogram_test_compliance_left_unit STRING,
  tympanogram_test_volume_left_unit STRING,
  tympanogram_test_width_left_unit STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.Batteries` (
  branch_id STRING,
  product_id STRING,
  description STRING,
  returnable STRING,
  batterysize STRING,
  catalog_no STRING,
  cell_quantity STRING,
  vendor_price STRING,
  client_price STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.Claims` (
  order_date STRING,
  delivery_date STRING,
  claim_id STRING,
  status_id STRING,
  order_id STRING,
  invoice_number STRING,
  order_total STRING,
  trip_name STRING,
  client_name STRING,
  client_id STRING,
  full_primary_insurer_name STRING,
  full_secondary_insurer_name STRING,
  primary_insurer_name STRING,
  secondary_insurer_name STRING,
  primary_insurer_claim_status STRING,
  secondary_insurer_claim_status STRING,
  pending_submission_amount STRING,
  patient_balance_zero STRING,
  submitted_date STRING,
  submitted_amount STRING,
  insurer_payment_amount STRING,
  insurer_credit_amount STRING,
  patient_payment_amount STRING,
  patient_credit_amount STRING,
  balance STRING,
  to_be_submitted_to_insurance STRING,
  patient_balance STRING,
  claim_balance STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.ClaimsLineItems` (
  branch_id STRING,
  order_id STRING,
  claim_id STRING,
  item_id STRING,
  item_type STRING,
  client_price STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.ClientALD` (
  branch_id STRING,
  client_id STRING,
  accessory_id STRING,
  order_id STRING,
  serial_number STRING,
  purchase_date STRING,
  warranty_expiry_date STRING,
  status STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.ClientAids` (
  branch_id STRING,
  client_id STRING,
  client_aid_id STRING,
  vendor_name STRING,
  model_id STRING,
  model_name STRING,
  side STRING,
  serial_number STRING,
  purchase_date STRING,
  warranty_expiry_date STRING,
  loss_and_damage_warranty STRING,
  color STRING,
  size_name STRING,
  state STRING,
  status STRING,
  client_price STRING,
  order_date STRING,
  received_date STRING,
  delivery_time STRING,
  returned_time STRING,
  notes STRING,
  service_plan_name STRING,
  service_plan_expiry_date STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.ClientCreditLines` (
  branch_id STRING,
  credit_id STRING,
  invoice_id STRING,
  order_id STRING,
  credit_line_memo STRING,
  credit_line_amount STRING,
  tax_name STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.ClientCredits` (
  branch_id STRING,
  credit_id STRING,
  client_id STRING,
  order_id STRING,
  invoice_id STRING,
  credit_time STRING,
  credit_amount STRING,
  credit_memo STRING,
  user STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.ClientDemographics` (
  branch_id STRING,
  client_id STRING,
  reference_number STRING,
  gender STRING,
  salutation STRING,
  surname STRING,
  given_name STRING,
  initial STRING,
  birthdate STRING,
  health_card_no STRING,
  unit STRING,
  street_no STRING,
  street_name STRING,
  city STRING,
  province_name STRING,
  country_name STRING,
  postal_code STRING,
  email_address STRING,
  home_telephone_no STRING,
  home_extension STRING,
  work_telephone_no STRING,
  work_extension STRING,
  mobile_telephone_no STRING,
  do_not_mail STRING,
  status STRING,
  status_id STRING,
  practitioner STRING,
  trip_name STRING,
  cash_sales_only STRING,
  referrer_type_id STRING,
  referral_source_id STRING,
  note STRING,
  created_time STRING,
  modified_time STRING,
  do_not_text STRING,
  do_not_email STRING,
  do_not_request_online_review STRING,
  do_not_send_commercial_messages STRING,
  quick_add STRING,
  quick_add_created_time STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.ClientGrouping` (
  branch_id STRING,
  client_id STRING,
  patient STRING,
  grouping_id STRING,
  grouping_name STRING,
  active STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.ClientInsurerCanada` (
  branch_id STRING,
  client_id STRING,
  insurer_name STRING,
  insurer_id STRING,
  insurer_type STRING,
  policy_number STRING,
  id_number STRING,
  active STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.ClientInsurerUS` (
  branch_id STRING,
  client_id STRING,
  insured_public_insurer_id STRING,
  insurer_name STRING,
  insured_id_number STRING,
  insured_name STRING,
  insured_relation STRING,
  insured_address STRING,
  insured_city STRING,
  insured_state STRING,
  insured_country STRING,
  insured_zip STRING,
  insured_telephone_no STRING,
  insured_policy_group_number STRING,
  insured_birthdate STRING,
  insured_gender STRING,
  insured_employer_school_name STRING,
  insured_plan_name STRING,
  estimated_benefit STRING,
  copay STRING,
  deductible STRING,
  pre_certified STRING,
  hearing_aid_benefit STRING,
  insured_notes STRING,
  sort_order STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.ClientJournal` (
  branch_id STRING,
  client_id STRING,
  journal_entry_id STRING,
  entry_time STRING,
  deleted_time STRING,
  entry_type STRING,
  user_text STRING,
  generated_text STRING,
  username STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.ClientJournalEvent` (
  branch_id STRING,
  event_id STRING,
  recurrence_id STRING,
  journal_entry_id STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.ClientMiscCredit` (
  branch_id STRING,
  credit_id STRING,
  client_id STRING,
  credit_time STRING,
  credit_amount STRING,
  credit_memo STRING,
  user STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.ClientMiscCreditInvoiceApplications` (
  branch_id STRING,
  credit_id STRING,
  order_id STRING,
  applied_amount STRING,
  applied_time STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.ClientMiscCreditRefundApplications` (
  branch_id STRING,
  credit_id STRING,
  refund_id STRING,
  applied_amount STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.ClientPaymentInvoiceApplications` (
  branch_id STRING,
  payment_id STRING,
  order_id STRING,
  applied_amount STRING,
  applied_time STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.ClientPaymentRefundApplications` (
  branch_id STRING,
  payment_id STRING,
  refund_id STRING,
  applied_amount STRING,
  applied_time STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.ClientPayments` (
  branch_id STRING,
  client_id STRING,
  payment_date STRING,
  payment_total STRING,
  payment_id STRING,
  payment_type STRING,
  card_number_suffix STRING,
  cheque_number STRING,
  memo STRING,
  pmt_method_id STRING,
  trip_id STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.ClientPhysician` (
  branch_id STRING,
  client_id STRING,
  physician_id STRING,
  surname STRING,
  given_name STRING,
  active STRING,
  sort_order STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.ClientRecall` (
  branch_id STRING,
  client_id STRING,
  recall_date STRING,
  recall_type STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.ClientRefund` (
  branch_id STRING,
  refund_id STRING,
  client_id STRING,
  pmt_method_desc STRING,
  refund_amount STRING,
  refund_time STRING,
  trip_name STRING,
  return_order_id STRING,
  return_applied_amount STRING,
  payment_id STRING,
  payment_applied_amount STRING,
  credit_id STRING,
  credit_applied_amount STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.ClientType` (
  branch_id STRING,
  client_id STRING,
  type_grouping_id STRING,
  type_grouping_desc STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.HearingAidModel` (
  branch_id STRING,
  vendor_name STRING,
  model_id STRING,
  model_name STRING,
  catalog_no STRING,
  vendor_price STRING,
  client_price STRING,
  active STRING,
  is_hearing_aid STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.InsuranceCompanies` (
  branch_id STRING,
  insurer_id STRING,
  insurer_type STRING,
  name STRING,
  address_1 STRING,
  address_2 STRING,
  city STRING,
  state STRING,
  zip STRING,
  phone STRING,
  fax STRING,
  revenue_group_desc STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.InsuranceCredits` (
  branch_id STRING,
  credit_id STRING,
  date_of_credit STRING,
  insurer_id STRING,
  insurance_company STRING,
  amount_paid STRING,
  invoice_number STRING,
  order_id STRING,
  insurer_type STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.InsuranceInvoices` (
  branch_id STRING,
  invoice_date STRING,
  invoice_number STRING,
  order_id STRING,
  client_id STRING,
  location STRING,
  insurance_company STRING,
  amount_billed STRING,
  insurer_type STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.InsuranceMiscCreditInvoiceApplications` (
  branch_id STRING,
  credit_id STRING,
  order_id STRING,
  insurer_id STRING,
  applied_amount STRING,
  applied_time STRING,
  insurer_type STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.InsuranceMiscCreditRefundApplications` (
  branch_id STRING,
  credit_id STRING,
  refund_id STRING,
  applied_amount STRING,
  insurer_type STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.InsuranceMiscCredits` (
  branch_id STRING,
  date_of_credit STRING,
  insurance_company STRING,
  amount_paid STRING,
  insurer_type STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.InsurancePaymentApplications` (
  branch_id STRING,
  public_insurer_id STRING,
  payment_id STRING,
  order_id STRING,
  applied_amount STRING,
  applied_time STRING,
  insurer_type STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.InsurancePaymentRefundApplications` (
  branch_id STRING,
  refund_id STRING,
  payment_id STRING,
  applied_amount STRING,
  applied_time STRING,
  insurer_type STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.InsurancePayments` (
  branch_id STRING,
  date_of_payment STRING,
  payment_amount STRING,
  insurance_company STRING,
  pmt_method_desc STRING,
  location STRING,
  insurer_type STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.InsuranceRefunds` (
  branch_id STRING,
  refund_id STRING,
  public_insurer_name STRING,
  pmt_method_desc STRING,
  refund_amount STRING,
  refund_time STRING,
  modified_time STRING,
  trip_name STRING,
  insurer_type STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.InsuranceReturnRefundApplications` (
  branch_id STRING,
  return_order_id STRING,
  refund_id STRING,
  public_insurer_id STRING,
  applied_amount STRING,
  insurer_type STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.InsuranceReturns` (
  branch_id STRING,
  return_order_id STRING,
  insurer_id STRING,
  credit_amount STRING,
  credit_id STRING,
  insurer_type STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.InvoiceLineItems` (
  branch_id STRING,
  order_id STRING,
  invoice_date STRING,
  invoice_number STRING,
  client_id STRING,
  item_id STRING,
  item STRING,
  quantity STRING,
  price STRING,
  discount STRING,
  discount_reason STRING,
  cost STRING,
  tax STRING,
  ha_side STRING,
  serial_number STRING,
  income_account STRING,
  expense_account STRING,
  catalog_no STRING,
  client_aid_id STRING,
  item_type STRING,
  prescriber_id STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.InvoiceMaster` (
  branch_id STRING,
  client_id STRING,
  order_id STRING,
  invoice_date STRING,
  invoice_number STRING,
  location STRING,
  provider STRING,
  order_total_with_tax STRING,
  total_tax STRING,
  returned STRING,
  amount_returned STRING,
  referrer_type_id STRING,
  referral_source_id STRING,
  sale_completed STRING,
  practitioner_id STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.Location` (
  branch_id STRING,
  trip_id STRING,
  trip_name STRING,
  unit STRING,
  street_no STRING,
  street_name STRING,
  city STRING,
  province STRING,
  postal_code STRING,
  telephone_no STRING,
  fax_no STRING,
  location_id STRING,
  location_name STRING,
  location_timezone STRING,
  company_name STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.OnlineBooking` (
  branch_id STRING,
  event_id STRING,
  recurrence_id STRING,
  contact_verified STRING,
  booking_state STRING,
  verified_user_id STRING,
  online_booking_secret STRING,
  booking_email_address STRING,
  referrer_domain STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.Physician` (
  branch_id STRING,
  physician_id STRING,
  surname STRING,
  given_name STRING,
  initial STRING,
  unit STRING,
  street_no STRING,
  street_name STRING,
  city STRING,
  email_address STRING,
  telephone_no STRING,
  fax_no STRING,
  npi STRING,
  postal_code STRING,
  province_name STRING,
  country_name STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.ReferralSources` (
  type_id STRING,
  source_id STRING,
  type_desc STRING,
  source_name STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.ReturnInvoiceApplications` (
  branch_id STRING,
  return_order_id STRING,
  order_id STRING,
  applied_amount STRING,
  applied_time STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.ReturnLineItems` (
  branch_id STRING,
  return_order_id STRING,
  order_id STRING,
  item_id STRING,
  return_quantity STRING,
  return_price STRING,
  return_discount STRING,
  item_type STRING,
  return_reason STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.ReturnRefundApplications` (
  branch_id STRING,
  return_order_id STRING,
  refund_id STRING,
  applied_amount STRING,
  applied_time STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.Returns` (
  branch_id STRING,
  return_order_id STRING,
  order_id STRING,
  client_id STRING,
  return_date STRING,
  modified_time STRING,
  return_total STRING,
  return_time STRING,
  trip_name STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.Services` (
  branch_id STRING,
  service_id STRING,
  service_name STRING,
  servicegroup STRING,
  returnable STRING,
  active STRING,
  catalog_no STRING,
  client_price STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.StockAid` (
  branch_id STRING,
  stock_aid_id STRING,
  location STRING,
  vendor_name STRING,
  model_name STRING,
  serial_number STRING,
  size_name STRING,
  color STRING,
  notes STRING,
  state STRING,
  received_date STRING,
  vendor_price STRING,
  return_date STRING,
  returned_date STRING,
  recall_date STRING,
  client_id STRING,
  received_time STRING,
  returned_time STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);

CREATE TABLE IF NOT EXISTS `{GCP_PROJECT}.Blueprint_PHI.User` (
  branch_id STRING,
  user_id STRING,
  username STRING,
  firstname STRING,
  lastname STRING,
  qualifications STRING,
  job_title STRING,
  active STRING,
  default_scheduling_location_id STRING,
  npi_number STRING,
  email_address STRING,
  photo STRING,
  _clinic_id STRING,
  _clinic_name STRING,
  _snapshot_date STRING
);
