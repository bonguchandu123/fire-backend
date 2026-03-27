#include <Servo.h>

int flame1    = 2;
int redLED    = 5;
int greenLED  = 6;
int relayPin  = 7;
int buzzer    = 8;
int servo1Pin = 9;
int servo2Pin = 10;

Servo servo1;
Servo servo2;

int  angle     = 0;
int  scanSpeed = 3;
int  fireAngle = 0;
bool systemOn  = true;

void setup() {
  Serial.begin(9600);
  pinMode(flame1,   INPUT);
  pinMode(redLED,   OUTPUT);
  pinMode(greenLED, OUTPUT);
  pinMode(relayPin, OUTPUT);
  pinMode(buzzer,   OUTPUT);
  servo1.attach(servo1Pin);
  servo2.attach(servo2Pin);

  digitalWrite(relayPin, HIGH);
  digitalWrite(redLED,   LOW);
  digitalWrite(greenLED, HIGH);
  digitalWrite(buzzer,   LOW);
  servo1.write(90);
  servo2.write(90);
  delay(1000);
  Serial.println("STATUS:ON");
}

void loop() {
  // Check for commands from PC
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd == "POWER_OFF") {
      systemOn = false;
      stopAll();
      Serial.println("STATUS:OFF");
    } else if (cmd == "POWER_ON") {
      systemOn = true;
      Serial.println("STATUS:ON");
    }
  }

  if (!systemOn) {
    delay(200);
    return;
  }

  int fire = digitalRead(flame1);

  Serial.print("Angle: ");
  Serial.println(angle);
  Serial.print("Sensor: ");
  Serial.println(fire);

  if (fire == LOW) {
    Serial.println("FIRE DETECTED!");
    fireAngle = angle;
    servo1.write(fireAngle);
    servo2.write(fireAngle);
    digitalWrite(redLED,   HIGH);
    digitalWrite(greenLED, LOW);
    digitalWrite(buzzer,   HIGH);
    digitalWrite(relayPin, LOW);
  } else {
    Serial.println("Scanning...");
    digitalWrite(redLED,   LOW);
    digitalWrite(greenLED, HIGH);
    digitalWrite(buzzer,   LOW);
    digitalWrite(relayPin, HIGH);

    angle += scanSpeed;
    if (angle >= 180 || angle <= 0) {
      scanSpeed = -scanSpeed;
    }
    servo1.write(angle);
    servo2.write(angle);
    delay(50);
  }
}

void stopAll() {
  digitalWrite(redLED,   LOW);
  digitalWrite(greenLED, LOW);
  digitalWrite(relayPin, HIGH);
  digitalWrite(buzzer,   LOW);
  servo1.write(90);
  servo2.write(90);
}